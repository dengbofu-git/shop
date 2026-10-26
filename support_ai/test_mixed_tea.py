import json
import re
from unittest import TestCase as UnitTestCase
from unittest.mock import Mock, patch

from django.test import TestCase
from langchain_core.runnables import Runnable, RunnableLambda

from .execution import execute_plan
from .planning import FiniteIntents, build_plan, explicit_requests, extract_requests, validate_plan
from .recommendation_options import BASIC_TEA_TYPES
from .context import context_from_turns
from .contracts import RecommendationIntent
from types import SimpleNamespace
from .tea_explanation import TeaExplanation
from . import test_grouped_recommendations as grouped_fixtures
from .tool_services import create_tool_handlers
from .workflow import ComplianceVerdict, DialogueResolution, build_graph
from .semantic_planning import SemanticPlan
from .grounding import GroundingReview


QUESTION = '说明不同茶种的区别，给出具体说明的茶种的推荐商品'


class ExplanationModel(Runnable):
    def __init__(self, bad_quote=False, allowed=None):
        self.bad_quote = bad_quote
        self.allowed = allowed

    def with_structured_output(self, schema):
        def structured(prompt):
            text = prompt.to_messages()[-1].content
            if schema is SemanticPlan:
                message = text.split('本轮原话：')[1].split('\n')[0]
                introduction, recommendation = message.split('，', 1)
                purchase = RecommendationIntent(action='SEARCH')
                match = re.search(r'每盒不超过(\d+)元', message)
                if match:
                    purchase = RecommendationIntent(action='SEARCH',
                        required={'price_max': match[1], 'currency': 'CNY', 'price_basis': 'unit'},
                        evidence=[{'field': 'required.' + field, 'value': value,
                                   'source': 'CURRENT', 'quote': match[0]}
                                  for field, value in [('price_max', match[1]), ('currency', 'CNY'), ('price_basis', 'unit')]])
                return SemanticPlan(action='new_request', standalone_question=message,
                    requests=[{'kind': 'question_answering', 'quote': introduction},
                              {'kind': 'recommendation', 'quote': recommendation}], purchase=purchase)
            if schema is TeaExplanation:
                data = json.loads(text)
                sections = []
                for category in data['categories']:
                    if self.allowed is not None and category not in self.allowed:
                        continue
                    ids = data['allowed_sources'][category]
                    if not ids:
                        continue
                    evidence = next(e for e in data['evidence'] if e['source_id'] == ids[0])
                    sections.append({'category': category, 'claims': [
                        {'text': category + '以所引资料的制造工艺为依据进行分类和区别。',
                         'citations': [{'source_id': ids[0], 'quote': '不是来源中的逐字引文' if self.bad_quote else evidence['text'][:100]}]}]})
                return TeaExplanation(sections=sections)
            if schema is GroundingReview:
                return GroundingReview(verdicts=[{'claim_id': row['claim_id'], 'supported': True,
                    'standalone': True, 'relevant': True} for row in json.loads(text)['claims']])
            if schema is DialogueResolution:
                return DialogueResolution(standalone_question=text.split('本轮：')[1].split('\n')[0], source_turn_ids=[], needs_clarification=False)
            if schema is RecommendationIntent:
                match = re.search(r'每盒不超过(\d+)元', text)
                if not match:
                    raise AssertionError('Unexpected model condition extraction')
                return RecommendationIntent(action='SEARCH', required={'price_max': match[1], 'currency': 'CNY', 'price_basis': 'unit'},
                    evidence=[{'field': 'required.' + field, 'value': value, 'source': 'CURRENT', 'quote': match[0]}
                              for field, value in [('price_max', match[1]), ('currency', 'CNY'), ('price_basis', 'unit')]])
            if schema is ComplianceVerdict:
                # A "safe" rewrite that drops sections must not erase the
                # deterministic explanation + matching product layout.
                return ComplianceVerdict(safe=True, revised_answer='一段省略了任务的总结')
            raise AssertionError('Unexpected schema: ' + schema.__name__)
        return RunnableLambda(structured)

    def invoke(self, input, config=None, **kwargs):
        raise AssertionError('Bound introduction/recommendation should not use a free-form composer')


def evidence_search(query):
    category = next(c for c in BASIC_TEA_TYPES if query.startswith(c))
    return [{'chunk_id': BASIC_TEA_TYPES.index(category) + 1, 'document_id': category,
             'text': category + '采用资料明确说明的制造工艺，与其他茶类的区别须根据具体工艺判断。',
             'source_title': category + '资料', 'source_reference': 'https://example.invalid/tea', 'metadata': {'year': 2026}}]


class MixedPlanningTests(UnitTestCase):
    def test_user_sentence_contains_two_ordered_tasks(self):
        plan = build_plan(explicit_requests(QUESTION), 'rules', QUESTION)
        self.assertEqual([s.intent for s in plan.steps], ['question_answering', 'recommendation'])
        self.assertEqual(plan.steps[0].request, '说明不同茶种的区别')
        self.assertEqual(plan.steps[1].knowledge_from, 's1')
        self.assertEqual(plan.steps[1].depends_on, ['s1'])
        self.assertEqual(plan.steps[0].tea_scope, list(BASIC_TEA_TYPES))

    def test_attributive_reference_is_not_a_second_knowledge_task(self):
        plan = build_plan(explicit_requests('推荐刚才介绍的茶类的商品'), 'rules', '')
        self.assertEqual([s.intent for s in plan.steps], ['recommendation'])

    def test_synonyms_and_coordinated_clauses_preserve_scopes(self):
        for verb in ('说明', '讲解', '阐述', '解释'):
            plan = build_plan(explicit_requests(verb + '绿茶和红茶的区别，并推荐对应商品'), 'rules', '')
            self.assertEqual(plan.steps[0].tea_scope, ['绿茶', '红茶'])
            self.assertEqual(plan.steps[1].knowledge_from, 's1')
        plan = build_plan(explicit_requests('介绍绿茶并推荐红茶'), 'rules', '')
        self.assertEqual(plan.steps[0].request, '介绍绿茶')
        self.assertEqual(plan.steps[1].request, '并推荐红茶')
        self.assertIsNone(plan.steps[1].knowledge_from)

    def test_forged_source_is_rejected(self):
        plan = build_plan(explicit_requests(QUESTION), 'rules', QUESTION)
        plan.steps[1].knowledge_from = 's2'
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_failed_introduction_skips_dependent_recommendation(self):
        plan = build_plan(explicit_requests(QUESTION), 'rules', QUESTION)
        from .execution import ToolResult
        query = Mock()
        values = execute_plan(plan, {'introduce_tea': lambda step, done: ToolResult(step_id=step.id, tool=step.tool, status='no_match'),
                                     'recommend_products': query})
        self.assertEqual([v.status for v in values], ['no_match', 'skipped'])
        query.assert_not_called()

    def test_uncovered_clause_uses_model_instead_of_short_circuiting(self):
        question = '梳理不同茶种的差别，推荐对应商品'
        model = Mock()
        model.with_structured_output.return_value = RunnableLambda(lambda prompt: FiniteIntents(requests=[
            {'kind': 'question_answering', 'quote': '梳理不同茶种的差别'}]))
        requests, source = extract_requests(model, question, question, [])
        self.assertEqual([r.kind for r in requests], ['question_answering', 'recommendation'])
        self.assertEqual(source, 'model')
        self.assertEqual(build_plan(requests, source, question).steps[1].knowledge_from, 's1')
        history = [{'intent': 'recommendation', 'assistant_text': '您想选择哪类茶？'}]
        requests, _ = extract_requests(model, question, question, history)
        self.assertEqual([r.kind for r in requests], ['question_answering', 'recommendation'])

    def test_constraints_and_negative_clauses_do_not_add_model_tasks(self):
        model = Mock()
        for question in ('每盒预算15元，推荐绿茶', '不要推荐商品，只介绍绿茶', '推荐绿茶，并给出理由'):
            extract_requests(model, question, question, [])
        model.with_structured_output.assert_not_called()

    def test_scoped_retrieval_shares_candidate_budget(self):
        from .configuration import AgentConfig
        from .retrieval import retrieve_scoped_knowledge
        config = AgentConfig(model='test', thinking='disabled', telemetry_enabled=False, export_enabled=False,
                             otlp_endpoint='', revision=1, retrieval_candidates=30)
        with patch('support_ai.retrieval.retrieve_knowledge', return_value=[]) as search:
            for category in BASIC_TEA_TYPES:
                retrieve_scoped_knowledge('query', None, config, category, list(BASIC_TEA_TYPES))
        budgets = [call.args[2].retrieval_candidates for call in search.call_args_list]
        self.assertEqual(budgets, [5] * 6)
        self.assertEqual(sum(budgets), config.retrieval_candidates)
        self.assertTrue(all(call.args[2].retrieval_top_k <= 2 for call in search.call_args_list))


class MixedTeaIntegrationTests(TestCase):
    databases = {'default', 'ai_storage'}

    def setUp(self):
        grouped_fixtures.GroupedRecommendationTests.setUp(self)

    def run_graph(self, question=QUESTION, model=None, search=evidence_search):
        model = model or ExplanationModel()
        return build_graph(model, tool_factory=lambda state: create_tool_handlers(
            model, search, state['safe_message'], state['resolved_question'], state.get('recent_turns', []), None, '[]')
        ).invoke({'message': question})

    def test_explanation_and_six_matching_product_groups_are_both_present(self):
        data = self.run_graph()['response']
        self.assertEqual(data['intents'], ['question_answering', 'recommendation'])
        self.assertEqual(data['explained_categories'], list(BASIC_TEA_TYPES))
        self.assertEqual([p['category'] for p in data['recommendations']], list(BASIC_TEA_TYPES))
        self.assertEqual([t['status'] for t in data['tasks']], ['success', 'success'])
        self.assertIn('制造工艺', data['answer'])
        self.assertIn('按茶类分别推荐', data['answer'])
        self.assertNotIn('省略了任务', data['answer'])

    def test_only_described_subset_is_recommended(self):
        data = self.run_graph(model=ExplanationModel(allowed=['绿茶', '红茶']))['response']
        self.assertEqual(data['explained_categories'], ['绿茶', '红茶'])
        self.assertEqual([p['category'] for p in data['recommendations']], ['绿茶', '红茶'])
        self.assertIn('证据不足', data['answer'])

    def test_empty_or_fabricated_evidence_never_unlocks_products(self):
        for model, search in [(ExplanationModel(), lambda query: []), (ExplanationModel(bad_quote=True), evidence_search)]:
            data = self.run_graph(model=model, search=search)['response']
            self.assertFalse(data['recommendations'])
            self.assertEqual([t['status'] for t in data['tasks']], ['no_match', 'skipped'])

    def test_explicit_pair_does_not_expand_to_all_six(self):
        data = self.run_graph('说明绿茶和红茶的区别，并推荐对应商品')['response']
        self.assertEqual(data['explained_categories'], ['绿茶', '红茶'])
        self.assertEqual([p['category'] for p in data['recommendations']], ['绿茶', '红茶'])

    def test_unknown_historical_reference_clarifies_without_recommending(self):
        plan = build_plan(explicit_requests('推荐刚才说明的茶种的商品'), 'rules', '')
        model = Mock()
        result = create_tool_handlers(model, None, plan.steps[0].request, '', [], None, '[]')['recommend_products'](plan.steps[0], {})
        self.assertEqual(result.status, 'needs_clarification')
        self.assertFalse(result.data['recommendations'])

    def test_budget_still_applies_to_knowledge_bound_groups(self):
        data = self.run_graph('说明绿茶和红茶的区别，并推荐对应商品，每盒不超过10元')['response']
        self.assertEqual(data['explained_categories'], ['绿茶', '红茶'])
        self.assertEqual([p['category'] for p in data['recommendations']], ['绿茶'])
        self.assertEqual(data['recommendation_groups'][1]['status'], 'no_match')
        self.assertEqual(data['product_intent']['required']['price_max'], '10.00')

    def test_verified_explanation_scope_survives_into_history(self):
        data = self.run_graph('说明绿茶和红茶的区别，并推荐对应商品')['response']
        history = context_from_turns([SimpleNamespace(pk=1, user_text='说明绿茶和红茶的区别，并推荐对应商品',
                                       answer=data['answer'], intent='multi_intent', response=data)])
        self.assertEqual(history[0]['explained_categories'], ['绿茶', '红茶'])
        question = '推荐刚才说明的茶种的商品'
        step = build_plan(explicit_requests(question), 'rules', question).steps[0]
        model = Mock()
        result = create_tool_handlers(model, None, question, question, history, None, '[]')['recommend_products'](step, {})
        self.assertEqual([p['category'] for p in result.data['recommendations']], ['绿茶', '红茶'])
        model.with_structured_output.assert_not_called()
