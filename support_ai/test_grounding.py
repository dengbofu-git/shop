"""Adversarial synthetic outputs; no provider, business DB or network is used."""
import json
import uuid
from unittest import TestCase
from unittest.mock import patch

from langchain_core.runnables import Runnable, RunnableLambda
from django.test import TestCase as DatabaseTestCase

from .grounding import (KnowledgeDraft, GroundingReview, GroundingUnavailable,
                        generate_grounded_answer, prepare_evidence, verify_claims)
from .business_grounding import make_answer_block, enforce_answer_consistency
from .workflow import build_graph, ComplianceVerdict
from .execution import ToolResult
from .tests import FakeModel


SOURCE = {'text': '绿茶采用杀青和干燥工艺，与红茶的加工步骤存在区别。',
          'source_title': '茶类工艺', 'source_reference': 'https://example.invalid/tea', 'metadata': {'year': 2026}}


def claim(text=None, quote=None, source_id='e1'):
    return {'text': text or SOURCE['text'], 'citations': [{'source_id': source_id, 'quote': quote or SOURCE['text']}]}


class ScriptedModel(Runnable):
    def __init__(self, drafts=None, reviewer=None):
        self.drafts = drafts or [[claim()]]
        self.reviewer = reviewer
        self.calls = []

    def with_structured_output(self, schema):
        def invoke(prompt):
            payload = json.loads(prompt.to_messages()[-1].content)
            count = sum(kind is schema for kind, _ in self.calls)
            self.calls.append((schema, payload))
            if schema is KnowledgeDraft:
                return {'claims': self.drafts[min(count, len(self.drafts) - 1)]}
            if schema is GroundingReview:
                if self.reviewer:
                    return self.reviewer(payload)
                return {'verdicts': [{'claim_id': c['claim_id'], 'supported': True, 'standalone': True,
                                     'relevant': True} for c in payload['claims']]}
            raise AssertionError('Unexpected schema')
        return RunnableLambda(invoke)

    def invoke(self, input, config=None, **kwargs):
        raise AssertionError('Unstructured generation is forbidden')


class ClaimGroundingTests(TestCase):
    def test_no_evidence_does_not_invoke_models_or_attach_sources(self):
        model = ScriptedModel()
        data, sources = generate_grounded_answer(model, '介绍绿茶', [])
        self.assertFalse(model.calls)
        self.assertFalse(sources)
        self.assertEqual(data['grounding']['status'], 'insufficient')

    def test_verified_claim_is_returned_with_exact_quote_and_source(self):
        data, sources = generate_grounded_answer(ScriptedModel(), '介绍绿茶', [SOURCE])
        self.assertIn(SOURCE['text'], data['answer'])
        self.assertEqual(data['grounding']['status'], 'verified')
        self.assertEqual(data['grounding']['claims'][0]['citations'][0]['quote'], SOURCE['text'])
        self.assertEqual(sources[0]['title'], '茶类工艺')
        self.assertEqual(data['grounding']['sources'][0]['source_id'],
                         data['grounding']['claims'][0]['citations'][0]['source_id'])
        self.assertEqual(data['grounding']['sources'][0]['url'], SOURCE['source_reference'])

    def test_unknown_id_or_fabricated_quote_never_reaches_reviewer(self):
        for row in [claim(source_id='e99'), claim(quote='这段原文实际并不存在')]:
            model = ScriptedModel(drafts=[[row]])
            data, sources = generate_grounded_answer(model, '介绍绿茶', [SOURCE])
            self.assertFalse(sources)
            self.assertEqual(data['grounding']['status'], 'insufficient')
            self.assertFalse(any(schema is GroundingReview for schema, _ in model.calls))
            self.assertEqual(data['grounding']['attempts'], 2)

    def test_new_numerals_are_rejected_even_if_model_would_approve(self):
        model = ScriptedModel(drafts=[[claim(text='绿茶必须使用80度的水冲泡。')]])
        data, _ = generate_grounded_answer(model, '介绍绿茶冲泡', [SOURCE])
        self.assertNotIn('80', data['answer'])
        self.assertFalse(any(schema is GroundingReview for schema, _ in model.calls))

    def test_knowledge_cannot_override_live_product_or_order_facts_even_with_a_quote(self):
        for text in ['这款绿茶单价为99元，可用库存10件。','您的订单已付款并已发货。','商家保证明天发货并送达。']:
            source = dict(SOURCE,text=text)
            model = ScriptedModel(drafts=[[claim(text=text,quote=text)]])
            data,sources = generate_grounded_answer(model,'介绍绿茶',[source])
            self.assertEqual(data['grounding']['status'],'insufficient')
            self.assertFalse(sources)
            self.assertFalse(any(schema is GroundingReview for schema,_ in model.calls))

    def test_market_amounts_are_not_rejected_just_for_mentioning_money(self):
        text = '资料记录2020年茶叶进口金额为100万美元。'
        data,sources = generate_grounded_answer(ScriptedModel(drafts=[[claim(text=text,quote=text)]]),
                                                '说明贸易数据',[dict(SOURCE,text=text)])
        self.assertEqual(data['grounding']['status'],'verified')
        self.assertTrue(sources)

    def test_real_quote_with_unsupported_extra_conclusion_is_rejected(self):
        def reject(payload):
            return {'verdicts': [{'claim_id': c['claim_id'], 'supported': False, 'standalone': True,
                                 'relevant': True} for c in payload['claims']]}
        model = ScriptedModel(drafts=[[claim(text='绿茶采用杀青工艺，而且所有绿茶均获得国际金奖。')]], reviewer=reject)
        data, sources = generate_grounded_answer(model, '介绍绿茶', [SOURCE])
        self.assertNotIn('金奖', data['answer'])
        self.assertFalse(sources)
        self.assertEqual(sum(schema is GroundingReview for schema, _ in model.calls), 2)

    def test_reviewer_receives_negated_full_context_not_only_cherry_picked_quote(self):
        source = dict(SOURCE, text='“绿茶采用杀青和干燥工艺”这一表述在本样品资料中未获证实。')
        def reject(payload):
            self.assertIn('未获证实', payload['sources'][0]['text'])
            return {'verdicts': [{'claim_id': 'c1', 'supported': False, 'standalone': True, 'relevant': True}]}
        model = ScriptedModel(reviewer=reject)
        accepted, _ = verify_claims(model, '介绍绿茶', [claim(quote='绿茶采用杀青和干燥工艺')], prepare_evidence([source]))
        self.assertFalse(accepted)

    def test_category_cannot_borrow_another_categories_valid_source(self):
        model = ScriptedModel()
        evidence = prepare_evidence([SOURCE, dict(SOURCE, text='红茶加工包含发酵和干燥等过程。')])
        accepted, issues = verify_claims(model, '介绍绿茶', [claim(source_id='e2', quote=evidence[1]['text'])], evidence, [['e1']])
        self.assertFalse(accepted)
        self.assertEqual(issues[0]['code'], 'INVALID_CITATION')
        self.assertFalse(model.calls)

    def test_missing_or_duplicate_verdict_is_a_technical_failure(self):
        for verdicts in [[], [{'claim_id':'c1','supported':True,'standalone':True,'relevant':True}]*2]:
            with self.subTest(verdicts=verdicts), self.assertRaises(GroundingUnavailable):
                generate_grounded_answer(ScriptedModel(reviewer=lambda p: {'verdicts': verdicts}), '介绍绿茶', [SOURCE])

    def test_reviewer_outage_never_becomes_supported_or_no_match(self):
        def broken(payload):
            raise TimeoutError('private transport diagnostic')
        with self.assertRaises(GroundingUnavailable) as caught:
            generate_grounded_answer(ScriptedModel(reviewer=broken), '介绍绿茶', [SOURCE])
        self.assertNotIn('private', str(caught.exception))

    def test_one_repair_can_replace_a_bad_claim(self):
        model = ScriptedModel(drafts=[[claim(source_id='e99')], [claim()]])
        data, sources = generate_grounded_answer(model, '介绍绿茶', [SOURCE])
        self.assertEqual(data['grounding']['attempts'], 2)
        self.assertEqual(data['grounding']['status'], 'verified')
        self.assertTrue(sources)
        drafts = [payload for schema,payload in model.calls if schema is KnowledgeDraft]
        self.assertEqual(drafts[1]['repair'][0]['claim']['citations'][0]['source_id'],'e99')

    def test_number_lists_are_not_merged_and_valid_thousands_keep_their_value(self):
        source = dict(SOURCE,text='绿茶样本的工艺参考编号是1，2。')
        model = ScriptedModel(drafts=[[claim(text='绿茶样本的工艺参考编号是12。',quote=source['text'])]])
        data,_ = generate_grounded_answer(model,'说明样本编号',[source])
        self.assertEqual(data['grounding']['status'],'insufficient')
        self.assertFalse(any(schema is GroundingReview for schema,_ in model.calls))
        source = dict(SOURCE,text='资料记录的茶叶进口金额为1,000.50万美元。')
        data,_ = generate_grounded_answer(ScriptedModel(drafts=[[claim(
            text='资料记录的茶叶进口金额为1000.50万美元。',quote=source['text'])]]),'说明贸易数据',[source])
        self.assertEqual(data['grounding']['status'],'verified')

    def test_partial_output_preserves_whole_standalone_units(self):
        bad = claim(text='因此它也可以获得国际认证。')
        def partial(payload):
            return {'verdicts': [{'claim_id': c['claim_id'], 'supported': c['claim_id']=='c1',
                'standalone': c['claim_id']=='c1', 'relevant': True} for c in payload['claims']]}
        data, sources = generate_grounded_answer(ScriptedModel(drafts=[[claim(), bad]],reviewer=partial), '介绍绿茶', [SOURCE])
        self.assertEqual(data['grounding']['status'], 'partial')
        self.assertIn(SOURCE['text'], data['answer'])
        self.assertNotIn('因此', data['answer'])
        self.assertEqual(len(data['grounding']['claims']), 1)
        self.assertEqual(len(sources), 1)

    def test_irrelevant_or_non_standalone_claims_are_not_published(self):
        for flags in [(True,False),(False,True)]:
            model = ScriptedModel(reviewer=lambda p: {'verdicts':[{'claim_id':'c1','supported':True,
                'standalone':flags[0],'relevant':flags[1]}]})
            data, sources = generate_grounded_answer(model, '介绍绿茶', [SOURCE])
            self.assertFalse(sources)
            self.assertEqual(data['grounding']['status'], 'insufficient')

    def test_evidence_budget_is_shared_and_source_ids_are_server_owned(self):
        evidence = prepare_evidence([dict(SOURCE,source_id='e99',text='茶'*500)]*30, 800)
        self.assertEqual([e['source_id'] for e in evidence], ['e1','e2'])
        self.assertEqual(sum(len(e['text']) for e in evidence), 800)

    def test_malformed_structure_gets_one_retry_then_is_a_technical_failure(self):
        model = ScriptedModel(drafts=[[{'text':'缺少引用的结构化结论'}]])
        with self.assertRaises(GroundingUnavailable):
            generate_grounded_answer(model,'介绍绿茶',[SOURCE])
        self.assertEqual(sum(schema is KnowledgeDraft for schema,_ in model.calls),2)

    def test_generator_transport_failure_does_not_become_evidence_insufficient(self):
        model = ScriptedModel()
        with patch.object(model,'with_structured_output',side_effect=TimeoutError('no transport')):
            with self.assertRaises(TimeoutError):
                generate_grounded_answer(model,'介绍绿茶',[SOURCE])


class TeaGroundingTests(TestCase):
    def test_valid_quote_but_unsupported_tea_claim_does_not_unlock_recommendation(self):
        from .test_mixed_tea import ExplanationModel, evidence_search, QUESTION
        from .tea_explanation import TeaExplanation
        from .tool_services import create_tool_handlers
        from .planning import build_plan, explicit_requests
        from .execution import execute_plan
        model = ExplanationModel()
        original = model.with_structured_output
        def structured(schema):
            if schema is GroundingReview:
                return RunnableLambda(lambda p: {'verdicts':[{'claim_id':c['claim_id'],'supported':False,
                    'standalone':True,'relevant':True} for c in json.loads(p.to_messages()[-1].content)['claims']]})
            return original(schema)
        with patch.object(model,'with_structured_output',side_effect=structured):
            handlers = create_tool_handlers(model,evidence_search,QUESTION,QUESTION,[],None,'[]')
            with patch.dict(handlers,recommend_products=lambda *args: self.fail('Ungrounded scope unlocked products')):
                results = execute_plan(build_plan(explicit_requests(QUESTION),'rules',QUESTION),handlers)
        self.assertEqual([r.status for r in results],['no_match','skipped'])
        self.assertFalse(results[0].sources)
        self.assertFalse(results[0].data['grounding']['claims'])

    def test_review_failure_is_error_and_independent_tasks_can_continue(self):
        from .test_mixed_tea import ExplanationModel, evidence_search, QUESTION
        from .tool_services import create_tool_handlers
        from .planning import build_plan, explicit_requests
        from .execution import execute_plan
        message = QUESTION
        model = ExplanationModel()
        original = model.with_structured_output
        def structured(schema):
            if schema is GroundingReview:
                raise TimeoutError('private provider error')
            return original(schema)
        with patch.object(model,'with_structured_output',side_effect=structured):
            handlers = create_tool_handlers(model,evidence_search,message,message,[],None,'[]')
            plan = build_plan(explicit_requests(message),'rules',message)
            # The server explicitly marks this second task independent.
            plan.steps[1].depends_on = []
            plan.steps[1].knowledge_from = None
            handlers['recommend_products'] = lambda step,done: ToolResult(
                step_id=step.id,tool=step.tool,status='success',data={'answer':'独立任务的程序结果。'})
            values = execute_plan(plan,handlers)
        self.assertEqual([v.status for v in values],['error','success'])
        self.assertEqual(values[0].status,'error')
        self.assertEqual(values[0].data['error_type'],'GroundingUnavailable')
        self.assertNotIn('private provider',str(values[0].model_dump()))


class BusinessFactConsistencyTests(TestCase):
    def setUp(self):
        self.blocks = [dict(step_id='s1',business=True,text='商品A：99 CNY，库存10件。'),
                       dict(step_id='s2',business=True,text='当前所选订单：待付款，尚未发货。')]
        self.original = '\n\n'.join(b['text'] for b in self.blocks)

    def test_changed_price_currency_stock_state_or_promise_discards_entire_rewrite(self):
        mutations = [('99','89'),('CNY','USD'),('10件','100件'),('待付款','已付款'),('尚未发货','已发货')]
        for old,new in mutations:
            text, check = enforce_answer_consistency(self.original.replace(old,new),self.blocks)
            self.assertEqual(text,self.original)
            self.assertTrue(check['rewrite_rejected'])
        text, check = enforce_answer_consistency(self.original+'明天一定送达。',self.blocks)
        self.assertNotIn('明天',text)
        self.assertTrue(check['rewrite_rejected'])

    def test_swapping_prices_between_products_is_not_accepted_as_same_numbers(self):
        blocks = [dict(step_id='s1',business=True,text='商品A：99元。商品B：80元。')]
        text, check = enforce_answer_consistency('商品A：80元。商品B：99元。',blocks)
        self.assertEqual(text,blocks[0]['text'])
        self.assertTrue(check['rewrite_rejected'])

    def test_unchanged_answer_passes(self):
        text, check = enforce_answer_consistency(self.original,self.blocks)
        self.assertEqual(text,self.original)
        self.assertFalse(check['rewrite_rejected'])
        self.assertEqual(check['protected_steps'],['s1','s2'])

    def test_product_details_are_rendered_from_dto_not_the_provided_prose(self):
        result = {'step_id':'s1','tool':'get_product_details','status':'success','data':{
            'answer':'商品售价1美元，已发货。','product_name':'模拟绿茶','specification':'50克',
            'category':'绿茶','price':'99.00','currency':'CNY','available_stock':10,'attributes':[]}}
        block = make_answer_block(result)
        self.assertIn('99.00 CNY',block['text'])
        self.assertIn('10件',block['text'])
        self.assertNotIn('1美元',block['text'])
        self.assertNotIn('已发货',block['text'])

    def test_missing_business_answer_never_triggers_free_form_generation(self):
        block = make_answer_block({'step_id':'s1','tool':'get_order_status','status':'success','data':{}})
        self.assertIn('没有可验证',block['text'])


class GraphFactConsistencyTests(TestCase):
    def test_safety_block_does_not_leak_rejected_prose_through_grounding_audit(self):
        text = '被安全检查拒绝的合成测试内容。'
        model = FakeModel({'recommendation':.1,'question_answering':.9,'after_sales':.1})
        original = model.with_structured_output
        def structured(schema):
            if schema is ComplianceVerdict:
                return RunnableLambda(lambda p: ComplianceVerdict(safe=False,revised_answer='不应发布的修订内容。'))
            return original(schema)
        with patch.object(model,'with_structured_output',side_effect=structured):
            result = build_graph(model,knowledge_search=lambda *args:[dict(SOURCE,text=text)]).invoke({'message':'介绍绿茶'})
        response = result['response']
        self.assertTrue(response['compliance_blocked'])
        self.assertNotIn(text,json.dumps(response,ensure_ascii=False))
        self.assertFalse(response['knowledge_sources'])
        self.assertEqual(response['grounding']['knowledge'][0]['status'],'blocked')
        self.assertFalse(response['grounding']['knowledge'][0]['claims'])
        self.assertFalse(response['grounding']['knowledge'][0]['sources'])

    def test_safe_but_false_compliance_rewrite_cannot_alter_mixed_order_facts(self):
        model = FakeModel({'recommendation':.1,'question_answering':.9,'after_sales':.1})
        original = model.with_structured_output
        def structured(schema):
            if schema is ComplianceVerdict:
                return RunnableLambda(lambda p: ComplianceVerdict(safe=True,revised_answer='订单已付款、已发货，商品仅1美元。'))
            return original(schema)
        def factory(state):
            def introduce(step,done):
                data,sources = generate_grounded_answer(model,step.request,[SOURCE])
                return ToolResult(step_id=step.id,tool=step.tool,status='success',data=data,sources=sources)
            def order(step,done):
                return ToolResult(step_id=step.id,tool=step.tool,status='success',
                                  data={'answer':'当前所选订单：待付款，尚未发货。','orders':[]})
            return {'introduce_tea':introduce,'get_order_status':order}
        with patch.object(model,'with_structured_output',side_effect=structured), patch.object(
                model,'invoke',side_effect=AssertionError('Unstructured composer must not run')):
            result = build_graph(model,tool_factory=factory).invoke({'message':'介绍绿茶，查询订单状态'})
        self.assertEqual(result['intents'],['question_answering','after_sales'])
        self.assertIn('待付款，尚未发货',result['answer'])
        self.assertIn(SOURCE['text'],result['answer'])
        self.assertNotIn('1美元',result['answer'])
        self.assertTrue(result['response']['grounding']['business_facts']['rewrite_rejected'])

    def test_empty_knowledge_cannot_produce_a_model_invented_answer(self):
        model = FakeModel({'recommendation':.1,'question_answering':.9,'after_sales':.1})
        result = build_graph(model).invoke({'message':'介绍绿茶'})
        self.assertEqual(result['response']['tasks'][0]['status'],'no_match')
        self.assertFalse(result['response']['knowledge_sources'])
        self.assertEqual(result['response']['grounding']['knowledge'][0]['claims'],[])


class GroundedHttpTests(DatabaseTestCase):
    databases = {'default','ai_storage'}

    def setUp(self):
        from users.models import UserProfile
        from tea_saas.utils import jwt_encode
        self.user = UserProfile.objects.create(username='grounding-buyer',is_active=True)
        self.auth = {'HTTP_AUTHORIZATION':'Bearer '+jwt_encode({'id':self.user.pk})}
        self.body = {'message':'介绍一下绿茶','request_id':str(uuid.uuid4())}

    def send(self, model):
        with patch('support_ai.model_client.configured_model',return_value=model), patch(
                'support_ai.retrieval.retrieve_knowledge',return_value=[SOURCE]):
            return self.client.post('/v1/support/chat/',data=json.dumps(self.body),
                                    content_type='application/json',**self.auth)

    def test_verified_claims_persist_and_idempotent_replay_does_not_run_model(self):
        from .models import SupportTurn
        response = self.send(FakeModel({'recommendation':.1,'question_answering':.9,'after_sales':.1}))
        self.assertEqual(response.status_code,200)
        data = response.json()
        self.assertEqual(data['grounding']['knowledge'][0]['status'],'verified')
        self.assertEqual(SupportTurn.objects.get().response['grounding'],data['grounding'])
        with patch('support_ai.model_client.configured_model',side_effect=AssertionError('Replay ran model')):
            replay = self.client.post('/v1/support/chat/',data=json.dumps(self.body),content_type='application/json',**self.auth)
        self.assertEqual(replay.json(),data)
        self.assertEqual(SupportTurn.objects.count(),1)

    def test_unsupported_claim_is_a_clear_no_match_without_source_badges(self):
        model = FakeModel({'recommendation':.1,'question_answering':.9,'after_sales':.1})
        original = model.with_structured_output
        def structured(schema):
            if schema is GroundingReview:
                return RunnableLambda(lambda p: {'verdicts':[{'claim_id':c['claim_id'],'supported':False,
                    'standalone':True,'relevant':True} for c in json.loads(p.to_messages()[-1].content)['claims']]})
            return original(schema)
        with patch.object(model,'with_structured_output',side_effect=structured):
            response = self.send(model)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['tasks'][0]['status'],'no_match')
        self.assertFalse(response.json()['knowledge_sources'])
        self.assertFalse(response.json()['grounding']['knowledge'][0]['claims'])

    def test_reviewer_failure_returns_503_and_never_saves_a_success_turn(self):
        from .models import SupportTurn
        model = FakeModel({'recommendation':.1,'question_answering':.9,'after_sales':.1})
        original = model.with_structured_output
        def structured(schema):
            if schema is GroundingReview:
                raise TimeoutError('private provider error')
            return original(schema)
        with patch.object(model,'with_structured_output',side_effect=structured):
            response = self.send(model)
        self.assertEqual(response.status_code,503)
        self.assertEqual(SupportTurn.objects.count(),0)
        self.assertNotIn('private provider',response.content.decode())
