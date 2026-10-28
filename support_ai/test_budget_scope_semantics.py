"""Semantic scope routing and application-owned evidence, with no remote model."""
import uuid
from unittest import TestCase as UnitTestCase

from django.test import TestCase
from langchain_core.runnables import Runnable, RunnableLambda

from goods.models import Catalog, SPU, SKU
from users.models import UserProfile
from .budget_scope import BudgetScopeDecision
from .contracts import RecommendationIntent, validate_recommendation_intent, validate_recommendation_branch
from .context import commit_turn, recent_context
from .models import SupportConversation
from .semantic_planning import plan_turn, SemanticPlan
from . import test_colloquial_budget as colloquial_fixtures
from .tool_services import create_tool_handlers
from .workflow import build_graph


class ScopeModel(Runnable):
    def __init__(self, decision, full_plan=None):
        self.decision, self.full_plan, self.calls = decision, full_plan, []

    def invoke(self, prompt, config=None, **kwargs):
        raise AssertionError('Unexpected free text generation')

    def with_structured_output(self, schema):
        def answer(prompt):
            self.calls.append((schema.__name__, prompt.to_messages()[-1].content))
            if schema is BudgetScopeDecision:
                return self.decision
            if schema is SemanticPlan and self.full_plan is not None:
                return self.full_plan
            raise AssertionError('Unexpected model stage: ' + schema.__name__)
        return RunnableLambda(answer)


def pending_history():
    # Reuse the contract-tested pending snapshot; storage projections have
    # separate integration tests below.
    fixture = colloquial_fixtures.ColloquialBudgetTests()
    fixture.setUp()
    return fixture.pending_history('推荐3000块左右的红茶')


class SemanticScopeUnitTests(UnitTestCase):
    def test_nonliteral_short_answers_accept_contextual_model_choice(self):
        for message, choice in (('总的', 'total'), ('全加起来', 'total'), ('后一种', 'total'),
                                ('一件的', 'unit'), ('不是每件，是全部算在一起', 'total'),
                                ('the whole lot', 'total')):
            with self.subTest(message=message):
                model = ScopeModel({'scope': choice, 'scope_only': True})
                history = pending_history()
                semantic, source, _ = plan_turn(model, message, history, None)
                intent = semantic.purchase
                self.assertEqual(source, 'model')
                self.assertEqual(intent.required.price_basis, choice)
                self.assertEqual(intent.required.budget_max if choice == 'total' else intent.required.price_max, '3000.00')
                self.assertEqual(intent.required.currency, 'CNY')
                self.assertEqual(intent.required.categories, ['红茶'])
                evidence = next(e for e in intent.evidence if e.field == 'required.price_basis')
                self.assertEqual(evidence.quote, message)
                self.assertEqual(evidence.context_turn_id, history[-1]['turn_id'])
                # Exercise the same second provenance check used by tools.
                validate_recommendation_intent(intent, message, history, None, branch_rules=False)
                validate_recommendation_branch(intent, tool='recommend_bundle' if choice == 'total' else 'recommend_products')
                self.assertEqual(len(model.calls), 1)

    def test_uncertain_reply_asks_only_the_pending_choice(self):
        semantic, _, previous = plan_turn(ScopeModel({'scope': 'uncertain', 'scope_only': True}), '都行吧', pending_history(), None)
        self.assertTrue(semantic.needs_clarification)
        self.assertIn('人民币3000', semantic.clarification_question)
        self.assertIn('每件商品', semantic.clarification_question)
        self.assertNotIn('完整说明', semantic.clarification_question)
        self.assertEqual(previous.purchase.required.price_max, '3000.00')

    def test_new_request_is_delegated_without_dropping_its_text(self):
        message = '算了，先聊聊制茶工艺'
        model = ScopeModel({'scope': 'uncertain', 'scope_only': False}, SemanticPlan(
            action='new_request', standalone_question=message,
            requests=[dict(kind='question_answering', quote=message)]))
        semantic, _, _ = plan_turn(model, message, pending_history(), None)
        self.assertEqual(semantic.requests[0].kind, 'question_answering')
        self.assertIsNone(semantic.purchase)
        self.assertEqual([name for name, _ in model.calls], ['BudgetScopeDecision', 'SemanticPlan'])

    def test_explicit_changed_money_bypasses_the_scope_only_classifier(self):
        message = '推荐总价2000元的红茶'
        model = ScopeModel({'scope': 'total', 'scope_only': True})
        semantic, source, _ = plan_turn(model, message, pending_history(), None)
        self.assertEqual(source, 'rules')
        self.assertEqual(semantic.purchase.required.budget_max, '2000.00')
        self.assertEqual(model.calls, [])

    def test_mixed_scope_and_new_money_keep_both_changes(self):
        message = '总的，改成2000元'
        model = ScopeModel(None, SemanticPlan(action='modify', standalone_question=message,
            requests=[dict(kind='recommendation', quote=message)], purchase=RecommendationIntent(
                action='SEARCH', required={'price_basis': 'total', 'budget_max': '2000.00'}, evidence=[
                    dict(field='required.price_basis', value='total', source='CURRENT', quote='总的'),
                    dict(field='required.budget_max', value='2000', source='CURRENT', quote='2000元')])))
        semantic, _, _ = plan_turn(model, message, pending_history(), None)
        self.assertEqual(semantic.purchase.required.budget_max, '2000.00')
        self.assertEqual(semantic.purchase.required.price_basis, 'total')
        self.assertEqual([name for name, _ in model.calls], ['SemanticPlan'])
        validate_recommendation_intent(semantic.purchase, message, pending_history(), None, branch_rules=False)

    def test_new_explicit_request_does_not_require_expired_old_amount(self):
        history = pending_history()
        history[-1]['dialogue_state']['purchase']['evidence'][0]['source_id'] = 'expired-turn'
        semantic, source, _ = plan_turn(ScopeModel(None), '推荐总价2000元的红茶', history, None)
        self.assertEqual(source, 'rules')
        self.assertEqual(semantic.purchase.required.budget_max, '2000.00')

    def test_bad_schema_cannot_change_money_or_fake_missing_user_information(self):
        history = pending_history()
        model = ScopeModel({'scope': 'total', 'scope_only': True, 'budget_max': '1.00'})
        with self.assertRaisesRegex(RuntimeError, 'output is invalid'):
            plan_turn(model, '总的', history, None)
        self.assertEqual(history[-1]['dialogue_state']['purchase']['required']['price_max'], '3000.00')

    def test_literal_validation_is_not_globally_relaxed(self):
        intent = RecommendationIntent(action='SEARCH', required={'price_basis': 'total'}, evidence=[
            dict(field='required.price_basis', value='total', source='CURRENT', quote='总的')])
        with self.assertRaises(ValueError):
            validate_recommendation_intent(intent, '总的', [], None, branch_rules=False)

    def test_no_pending_slot_does_not_use_the_scope_classifier(self):
        message = '总的'
        model = ScopeModel({'scope': 'total', 'scope_only': True}, SemanticPlan(
            action='clarify', standalone_question=message, requests=[dict(kind='clarification', quote=message)],
            needs_clarification=True, clarification_question='请说明希望咨询的内容。'))
        semantic, _, _ = plan_turn(model, message, [], None)
        self.assertIsNone(semantic.purchase)
        self.assertEqual([name for name, _ in model.calls], ['SemanticPlan'])


class SemanticScopeStorageTests(TestCase):
    def setUp(self):
        self.user = UserProfile.objects.create(username='semantic-scope-buyer', is_active=True)
        category = Catalog.objects.create(name='红茶')
        product = SPU.objects.create(name='合成语义茶', catalog=category)
        SKU.objects.create(spu=product, name='合成规格', price='750.00', market_price='750.00',
                           cost_price='100.00', stock=10, is_launched=True)

    def graph(self, model):
        return build_graph(model, tool_factory=lambda state: create_tool_handlers(
            model, None, state['safe_message'], state['resolved_question'], state.get('recent_turns', []), None))

    def start(self, model):
        response = self.graph(model).invoke({'message': '推荐3000块的茶'})['response']
        saved = commit_turn(self.user, None, 0, uuid.uuid4(), 'first', '推荐3000块的茶', response)
        return SupportConversation.objects.get(pk=saved['conversation_id'])

    def resolved(self):
        model = ScopeModel({'scope': 'total', 'scope_only': True})
        conversation = self.start(model)
        response = self.graph(model).invoke({'message': '总的', 'recent_turns': recent_context(conversation)})['response']
        self.assertEqual(response['tasks'][0]['tool'], 'recommend_bundle')
        self.assertEqual(response['recommendation_status'], 'MATCHED')
        self.assertEqual(response['recommendation_bundles'][0]['subtotal'], '3000.00')
        commit_turn(self.user, conversation, 1, uuid.uuid4(), 'reply', '总的', response)
        return conversation, response

    def test_saved_nonliteral_scope_survives_future_money_change(self):
        conversation, _ = self.resolved()
        message = '把预算改成2000元'
        model = ScopeModel(None, SemanticPlan(action='modify', standalone_question=message,
            requests=[dict(kind='recommendation', quote=message)], purchase=RecommendationIntent(
                action='SEARCH', required={'budget_max': '2000.00'}, evidence=[
                    dict(field='required.budget_max', value='2000', source='CURRENT', quote='2000元')])))
        response = self.graph(model).invoke({'message': message, 'recent_turns': recent_context(conversation)})['response']
        self.assertEqual(response['product_intent']['required']['budget_max'], '2000.00')
        self.assertEqual(response['product_intent']['required']['price_basis'], 'total')
        self.assertEqual(response['diagnostics'], [])
        self.assertEqual(response['tasks'][0]['tool'], 'recommend_bundle')
        self.assertNotIn('context_turn_id', model.calls[0][1])
        self.assertNotIn('budget_scope_evidence', model.calls[0][1])

    def test_missing_saved_interpretation_or_origin_is_rejected(self):
        conversation, response = self.resolved()
        history = recent_context(conversation)
        self.assertTrue(history[-1].get('budget_scope_evidence'))
        intent = history[-1]['dialogue_state']['purchase']
        validate_recommendation_intent(intent, '', history, None, branch_rules=False)
        history[-1].pop('budget_scope_evidence')
        with self.assertRaises(ValueError):
            validate_recommendation_intent(intent, '', history, None, branch_rules=False)
        other = recent_context(conversation)[-1:]
        with self.assertRaises(ValueError):
            validate_recommendation_intent(intent, '', other, None, branch_rules=False)

    def test_other_conversation_cannot_reuse_the_context_reference(self):
        conversation, response = self.resolved()
        other = self.start(ScopeModel(None))
        intent = response['product_intent']
        with self.assertRaises(ValueError):
            validate_recommendation_intent(intent, '总的', recent_context(other), None, branch_rules=False)

    def test_uncertain_scope_keeps_pending_state_and_returns_specific_question(self):
        model = ScopeModel({'scope': 'uncertain', 'scope_only': True})
        conversation = self.start(model)
        response = self.graph(model).invoke({'message': '都可以', 'recent_turns': recent_context(conversation)})['response']
        self.assertIn('人民币3000', response['answer'])
        self.assertNotIn('完整说明', response['answer'])
        self.assertEqual(response['dialogue_state']['status'], 'pending')
        self.assertEqual(response['dialogue_state']['purchase']['required']['price_max'], '3000.00')
