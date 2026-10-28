"""Provider-boundary and graph budget regressions; no network or real models."""
import json
from concurrent.futures import ThreadPoolExecutor
from unittest import TestCase
from unittest.mock import patch

import httpx
from django.test import override_settings
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel

from .cost_control import (CostPolicy, ModelBudgetExceeded, RequestBudget, model_request,
                           current_budget, BudgetedGraph)
from .model_client import AgentModel, SupportChatOpenAI, configured_model
from .grounding import KnowledgeDraft, GroundingReview, generate_grounded_answer
from .test_grounding import ScriptedModel, SOURCE, claim
from .budget_scope import BudgetScopeDecision


class Slot(BaseModel):
    value: str


class ProviderBudgetTests(TestCase):
    def setUp(self):
        self.requests = []
        def reply(request):
            body = json.loads(request.content)
            self.requests.append(body)
            tool = body['tools'][0]['function']['name']
            return httpx.Response(200, json={
                'id': 'test-' + str(len(self.requests)), 'model': 'deepseek-flash', 'object': 'chat.completion',
                'choices': [{'index': 0, 'finish_reason': 'tool_calls', 'message': {
                    'role': 'assistant', 'content': None, 'tool_calls': [{'id': 'call_test', 'type': 'function',
                        'function': {'name': tool, 'arguments': json.dumps(
                            {'claims': []} if tool == 'KnowledgeDraft' else
                            {'verdicts': []} if tool == 'GroundingReview' else
                            {'scope': 'total', 'scope_only': True} if tool == 'BudgetScopeDecision' else {'value': '绿茶'})}}]}}],
                'usage': {'prompt_tokens': 40, 'completion_tokens': 10, 'total_tokens': 50}})
        self.transport = httpx.MockTransport(reply)
        self.http = httpx.Client(transport=self.transport)
        client = SupportChatOpenAI(model='deepseek-flash', api_key='synthetic-no-network',
                                  base_url='https://example.invalid/v1', http_client=self.http, max_retries=0)
        self.model = AgentModel(client, 'enabled')

    def tearDown(self):
        self.http.close()

    def test_default_non_thinking_and_real_wire_max_tokens(self):
        with model_request() as budget:
            parsed = self.model.with_structured_output(Slot).invoke([HumanMessage(content='推荐绿茶')])
        self.assertEqual(parsed.value, '绿茶')
        self.assertEqual(self.requests[0]['thinking'], {'type': 'disabled'})
        self.assertEqual(self.requests[0]['max_tokens'], 1600)
        self.assertNotIn('max_completion_tokens', self.requests[0])
        self.assertEqual(budget.snapshot()['input_tokens'], 40)
        self.assertEqual(budget.snapshot()['output_tokens'], 10)

    def test_call_kwargs_cannot_override_limits(self):
        with model_request():
            with self.assertRaises(ValueError):
                self.model.invoke('绿茶', max_tokens=99999)
        self.assertFalse(self.requests)

    def test_knowledge_and_verification_have_separate_wire_caps(self):
        with model_request() as budget:
            self.model.with_structured_output(KnowledgeDraft).invoke('介绍绿茶')
            self.model.with_structured_output(GroundingReview).invoke('检查证据')
        self.assertEqual([r['max_tokens'] for r in self.requests], [2400, 768])
        self.assertEqual(budget.snapshot()['stages'], {'knowledge': 1, 'verification': 1})

    def test_scope_classifier_uses_small_non_thinking_stage(self):
        with model_request() as budget:
            result = self.model.with_structured_output(BudgetScopeDecision).invoke('合成口径选择')
        self.assertEqual(result.scope, 'total')
        self.assertEqual(self.requests[0]['max_tokens'], 192)
        self.assertEqual(self.requests[0]['thinking'], {'type': 'disabled'})
        self.assertEqual(budget.snapshot()['stages'], {'scope': 1})

    @override_settings(SUPPORT_EXTRACTION_THINKING='enabled')
    def test_explicit_thinking_uses_schema_json_mode_with_correct_wire_cap(self):
        sent = []
        def reply(request):
            sent.append(json.loads(request.content))
            return httpx.Response(200, json={'id':'json','model':'deepseek-flash',
                'choices':[{'index':0,'finish_reason':'stop','message':{
                    'role':'assistant','content':'{"value":"green tea"}'}}],
                'usage':{'prompt_tokens':40,'completion_tokens':10,'total_tokens':50}})
        with httpx.Client(transport=httpx.MockTransport(reply)) as http:
            client = SupportChatOpenAI(model='deepseek-flash', api_key='synthetic',
                base_url='https://example.invalid/v1', http_client=http, max_retries=0)
            with model_request():
                result = AgentModel(client,'enabled').with_structured_output(Slot).invoke('介绍绿茶')
        self.assertEqual(result.value, 'green tea')
        self.assertEqual(sent[0]['thinking'], {'type':'enabled'})
        self.assertEqual(sent[0]['response_format'], {'type':'json_object'})
        self.assertEqual(sent[0]['max_tokens'], 1600)
        self.assertIn('JSON Schema', sent[0]['messages'][0]['content'])

    @override_settings(SUPPORT_MODEL_MAX_CALLS=1)
    def test_separate_clients_share_one_turn_and_block_before_transport(self):
        with model_request() as budget:
            self.model.with_structured_output(Slot).invoke('绿茶')
            other = AgentModel(self.model.client, 'enabled')
            with self.assertRaises(ModelBudgetExceeded):
                other.with_structured_output(Slot).invoke('红茶')
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(budget.snapshot()['rejected_calls'], 1)

    @override_settings(SUPPORT_MODEL_MAX_OUTPUT_TOKENS=11)
    def test_remaining_output_is_sent_to_provider(self):
        with model_request() as budget:
            self.model.with_structured_output(Slot).invoke('绿茶')
            self.model.with_structured_output(Slot).invoke('红茶')
            with self.assertRaises(ModelBudgetExceeded):
                self.model.with_structured_output(Slot).invoke('白茶')
        self.assertEqual([r['max_tokens'] for r in self.requests], [11, 1])
        # The synthetic provider exceeds its second cap; account actual usage,
        # stop further calls, and never pretend an overrun can be undone.
        self.assertEqual(budget.snapshot()['output_tokens'], 20)

    @override_settings(SUPPORT_MODEL_MAX_INPUT_TOKENS=1)
    def test_input_admission_prevents_provider_call(self):
        with model_request():
            with self.assertRaises(ModelBudgetExceeded):
                self.model.with_structured_output(Slot).invoke('绿茶')
        self.assertFalse(self.requests)

    def test_timeout_keeps_reservation_and_no_sdk_retry(self):
        hits = []
        def fail(request):
            hits.append(1)
            raise httpx.ReadTimeout('synthetic transport timeout', request=request)
        with httpx.Client(transport=httpx.MockTransport(fail)) as http:
            with patch('support_ai.model_client.SupportChatOpenAI', wraps=SupportChatOpenAI) as factory:
                # configured_model always disables hidden retries, even if an
                # old caller still asks for them.
                with override_settings(SUPPORT_API_KEY='synthetic', SUPPORT_BASE_URL='https://example.invalid',
                                       SUPPORT_MODEL='deepseek-flash', SUPPORT_THINKING='enabled'):
                    model = configured_model(max_retries=4)
                self.assertEqual(factory.call_args.kwargs['max_retries'], 0)
            model = AgentModel(SupportChatOpenAI(model='deepseek-flash', api_key='synthetic',
                base_url='https://example.invalid/v1', http_client=http, max_retries=0), 'enabled')
            with model_request() as budget:
                with self.assertRaises(Exception):
                    model.with_structured_output(Slot).invoke('绿茶')
        self.assertEqual(hits, [1])
        self.assertEqual(budget.snapshot()['unknown_usage_calls'], 1)
        self.assertEqual(budget.snapshot()['output_tokens'], 1600)

    @override_settings(SUPPORT_VERIFICATION_THINKING='enabled')
    def test_stage_policy_can_enable_only_verification(self):
        with model_request() as budget:
            self.assertEqual(budget.stage_policy['verification'][0], 'enabled')
            self.assertEqual(budget.stage_policy['planning'][0], 'disabled')
            self.assertEqual(budget.stage_policy['knowledge'][0], 'disabled')

    def test_malformed_output_is_billed_before_parse_error(self):
        def malformed(request):
            body = json.loads(request.content)
            return httpx.Response(200, json={'id':'bad','model':'deepseek-flash',
                'choices':[{'index':0,'finish_reason':'tool_calls','message':{'role':'assistant','content':None,
                    'tool_calls':[{'id':'call_bad','type':'function','function':{
                        'name':body['tools'][0]['function']['name'],'arguments':'{"value":123}'}}]}}],
                'usage':{'prompt_tokens':45,'completion_tokens':7,'total_tokens':52}})
        with httpx.Client(transport=httpx.MockTransport(malformed)) as http:
            client = SupportChatOpenAI(model='deepseek-flash', api_key='synthetic',
                base_url='https://example.invalid/v1', http_client=http, max_retries=0)
            with model_request() as budget:
                with self.assertRaises(Exception):
                    AgentModel(client,'enabled').with_structured_output(Slot).invoke('绿茶')
        self.assertEqual(budget.snapshot()['output_tokens'], 7)
        self.assertEqual(budget.snapshot()['unknown_usage_calls'], 0)


class RequestIsolationTests(TestCase):
    def test_status_only_is_not_enough_to_skip_verification(self):
        from .business_grounding import needs_model_review
        for status in ['verified', 'partial', 'insufficient']:
            result = {'tool':'introduce_tea','status':'success','data':{
                'answer':'未经核验的合成结论。','grounding':{'status':status}}}
            self.assertTrue(needs_model_review([result]))

    def test_exhausted_review_does_not_publish_unverified_prose(self):
        from .tests import FakeModel
        from .workflow import build_graph, ComplianceVerdict
        from .execution import ToolResult
        model = FakeModel({'recommendation':.1,'question_answering':.9,'after_sales':.1})
        original = model.with_structured_output
        def structured(schema):
            if schema is ComplianceVerdict:
                def exhausted(_):
                    raise ModelBudgetExceeded('synthetic review exhaustion')
                return RunnableLambda(exhausted)
            return original(schema)
        def factory(state):
            def introduce(step, done):
                return ToolResult(step_id=step.id, tool=step.tool, status='success',
                                  data={'answer':'未经核验的合成结论。'})
            return {'introduce_tea':introduce}
        with patch.object(model,'with_structured_output',side_effect=structured):
            result = build_graph(model,tool_factory=factory).invoke({'message':'介绍绿茶'})
        self.assertTrue(result['response']['compliance_blocked'])
        self.assertNotIn('未经核验',result['response']['answer'])

    def test_context_reaches_actual_langgraph_node_and_nested_clients(self):
        from langgraph.graph import StateGraph, START, END
        def node(state):
            budget = current_budget()
            self.assertIsNotNone(budget)
            reservation = budget.reserve('rewrite', 10, 20)
            budget.settle(reservation, {'input_tokens': 5, 'output_tokens': 10})
            return {'response': {'answer': '固定测试结果'}}
        graph = StateGraph(dict)
        graph.add_node('test', node)
        graph.add_edge(START, 'test')
        graph.add_edge('test', END)
        result = BudgetedGraph(graph.compile()).invoke({})
        self.assertEqual(result['response']['model_usage']['stages'], {'rewrite': 1})
        self.assertIsNone(current_budget())

    def test_exhaustion_does_not_block_independent_program_tool(self):
        from .execution import execute_plan, ToolResult
        from .planning import build_plan, explicit_requests
        question = '介绍绿茶，推荐红茶'
        requests = explicit_requests(question)
        plan = build_plan(requests, 'rules', question)
        def knowledge(step, done):
            raise ModelBudgetExceeded('synthetic exhaustion')
        def products(step, done):
            return ToolResult(step_id=step.id, tool=step.tool, status='success', data={'answer': '程序商品结果'})
        values = execute_plan(plan, {'introduce_tea': knowledge, 'recommend_products': products})
        self.assertEqual([v.status for v in values], ['error', 'success'])
        self.assertIn('预算', values[0].data['answer'])

    def test_graph_requests_are_isolated_and_context_reaches_graph_workers(self):
        def consume(_):
            budget = current_budget()
            r = budget.reserve('planning', 10, 10)
            budget.settle(r, {'input_tokens': 10, 'output_tokens': 5})
            return {'response': {'answer': '固定测试结果'}}
        graph = BudgetedGraph(RunnableLambda(consume))
        with ThreadPoolExecutor(max_workers=2) as pool:
            values = list(pool.map(graph.invoke, [1, 2]))
        self.assertEqual([r['model_usage']['calls'] for r in values], [1, 1])
        self.assertIsNone(current_budget())

    def test_unknown_usage_is_reserved_and_parallel_admission_is_atomic(self):
        budget = RequestBudget(CostPolicy(max_calls=1, max_input_tokens=100, max_output_tokens=100))
        def reserve(_):
            try:
                return budget.reserve('planning', 10, 40)
            except ModelBudgetExceeded:
                return None
        with ThreadPoolExecutor(max_workers=4) as pool:
            reservations = list(pool.map(reserve, range(4)))
        accepted = [r for r in reservations if r is not None]
        self.assertEqual(len(accepted), 1)
        budget.settle(accepted[0], None)
        self.assertEqual(budget.snapshot()['output_tokens'], 40)

    def test_partial_knowledge_uses_one_generation_and_one_verification(self):
        def review(payload):
            return {'verdicts':[{'claim_id':c['claim_id'],'supported':c['claim_id']=='c1',
                                'standalone':True,'relevant':True} for c in payload['claims']]}
        model = ScriptedModel(drafts=[[claim(), claim(text='这款绿茶已获得国际金奖认证。')]], reviewer=review)
        data, _ = generate_grounded_answer(model, '介绍绿茶', [SOURCE])
        self.assertEqual(data['grounding']['status'], 'partial')
        self.assertEqual([s for s,_ in model.calls], [KnowledgeDraft, GroundingReview])
        self.assertNotIn('金奖', data['answer'])
