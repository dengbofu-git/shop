"""Synthetic semantic responses exercise validation, not live model accuracy."""
from unittest import TestCase

from langchain_core.runnables import Runnable, RunnableLambda

from .contracts import RecommendationIntent
from .semantic_planning import DialogueState, SemanticPlan, plan_turn, response_state


class PlanModel(Runnable):
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def with_structured_output(self, schema):
        if schema is not SemanticPlan:
            raise AssertionError('Unexpected structured schema')

        def invoke(prompt):
            self.calls.append(prompt.to_messages()[-1].content)
            return self.payload
        return RunnableLambda(invoke)

    def invoke(self, input, config=None, **kwargs):
        raise AssertionError('No free-form answer expected')


class SemanticPlanningTests(TestCase):
    def history(self):
        message = '推荐两款绿茶，每盒不超过50'
        purchase = RecommendationIntent(action='CLARIFY',
            required={'categories': ['绿茶'], 'price_max': '50', 'price_basis': 'unit'},
            missing_fields=['currency'], evidence=[
                {'field': 'required.' + field, 'value': value, 'quote': quote,
                 'source': 'CONTEXT', 'source_id': 't1'} for field, value, quote in [
                     ('categories', '绿茶', '绿茶'), ('price_max', '50', '每盒不超过50'),
                     ('price_basis', 'unit', '每盒')]])
        state = DialogueState(status='pending', task='recommendation', request=message,
                              purchase=purchase, limit=2, missing_fields=['currency'])
        return [{'turn_id': 't1', 'user_text': message, 'assistant_text': '请确认币种。',
                 'dialogue_state': state.model_dump()}]

    def test_currency_supplement_preserves_budget_category_count_and_evidence(self):
        payload = {'action': 'supplement', 'standalone_question': '推荐两款绿茶，每盒不超过50美元',
            'source_turn_ids': ['t1'], 'requests': [{'kind': 'recommendation', 'quote': '美元'}],
            'purchase': {'action': 'SEARCH', 'required': {'currency': 'USD'}, 'evidence': [
                {'field': 'required.currency', 'value': 'USD', 'source': 'CURRENT', 'quote': '美元'}]}}
        model = PlanModel(payload)
        plan, source, previous = plan_turn(model, '美元', self.history(), None)
        self.assertEqual(source, 'model')
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(plan.purchase.required.categories, ['绿茶'])
        self.assertEqual(plan.purchase.required.price_max, '50.00')
        self.assertEqual(plan.purchase.required.currency, 'USD')
        self.assertEqual(plan.purchase.required.price_basis, 'unit')
        self.assertEqual(plan.purchase.action, 'SEARCH')
        self.assertFalse(plan.purchase.missing_fields)
        saved = response_state(plan, {}, previous)
        self.assertEqual(saved['limit'], 2)
        self.assertEqual(saved['status'], 'completed')

    def test_expired_evidence_cannot_turn_a_budgeted_task_into_unfiltered_search(self):
        history = self.history()
        history[0]['dialogue_state']['purchase']['evidence'][0]['source_id'] = 'expired-turn'
        payload = {'action': 'supplement', 'standalone_question': '美元',
                   'requests': [{'kind': 'recommendation', 'quote': '美元'}],
                   'purchase': {'action': 'SEARCH', 'required': {'currency': 'USD'}, 'evidence': [
                       {'field': 'required.currency', 'value': 'USD', 'source': 'CURRENT', 'quote': '美元'}]}}
        with self.assertRaises(ValueError):
            plan_turn(PlanModel(payload), '美元', history, None)

    def test_clear_budget_requires_explicit_scope_and_removes_all_budget_fields(self):
        message = '取消预算限制'
        payload = {'action': 'modify', 'standalone_question': message,
            'requests': [{'kind': 'recommendation', 'quote': message}],
            'purchase': {'action': 'SEARCH'},
            'clear_fields': ['required.' + f for f in ('price_min', 'price_max', 'currency', 'price_basis')]}
        plan, _, _ = plan_turn(PlanModel(payload), message, self.history(), None)
        self.assertEqual(plan.purchase.required.categories, ['绿茶'])
        for field in ('price_min', 'price_max', 'currency', 'price_basis'):
            self.assertIsNone(getattr(plan.purchase.required, field))
        payload['requests'][0]['quote'] = '取消品牌限制'
        payload['standalone_question'] = '取消品牌限制'
        with self.assertRaises(ValueError):
            plan_turn(PlanModel(payload), '取消品牌限制', self.history(), None)

    def test_new_explicit_request_does_not_inherit_old_budget(self):
        model = PlanModel(None)
        plan, source, _ = plan_turn(model, '推荐白茶', self.history(), None)
        self.assertEqual(source, 'rules')
        self.assertEqual(plan.action, 'new_request')
        self.assertEqual(plan.purchase.required.categories, ['白茶'])
        self.assertIsNone(plan.purchase.required.price_max)
        self.assertFalse(model.calls)

    def test_exact_six_type_grouping_is_not_invented_as_six_hard_filters(self):
        from .planning import build_plan
        message = '按照六种基本茶类各推荐一款，并给出理由'
        model = PlanModel(None)
        plan, source, _ = plan_turn(model, message, self.history(), None)
        self.assertEqual(source, 'rules')
        self.assertFalse(model.calls)
        self.assertFalse(plan.purchase.required.categories)
        self.assertIsNone(plan.purchase.required.price_max)
        task = build_plan(plan.requests, source, message).steps[0]
        self.assertEqual(task.recommendation.mode, 'by_category')
        self.assertEqual(task.recommendation.per_category_limit, 1)

    def test_grouping_shortcut_never_discards_extra_constraints(self):
        for suffix in ('，每盒不超过20美元', '，不要红茶', '，只要有机认证的商品'):
            model = PlanModel(None)
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                plan_turn(model, '按照六种基本茶类各推荐一款' + suffix, [], None)
            self.assertEqual(len(model.calls), 1)

    def test_cancel_clears_state_and_greeting_preserves_it_without_model_calls(self):
        for message, keep in [('取消当前任务', False), ('你好', True)]:
            with self.subTest(message=message):
                model = PlanModel(None)
                plan, _, previous = plan_turn(model, message, self.history(), None)
                saved = response_state(plan, {}, previous)
                self.assertEqual(saved, previous.model_dump() if keep else DialogueState().model_dump())
                self.assertFalse(model.calls)

    def test_unknown_and_out_of_bounds_product_references_are_rejected(self):
        history = self.history()
        history[0]['product_references'] = [{'sku_id': 1, 'name': '测试规格'}]
        for turn_id, position in [('t1', 2), ('foreign-turn', 1)]:
            payload = {'action': 'follow_up', 'standalone_question': '第二款多少钱',
                'source_turn_ids': [turn_id],
                'requests': [{'kind': 'product_details', 'quote': '第二款多少钱'}],
                'result_reference': {'turn_id': turn_id, 'position': position}}
            with self.subTest(turn_id=turn_id), self.assertRaises(ValueError):
                plan_turn(PlanModel(payload), '第二款多少钱', history, None)

    def test_preference_canonicalization_requires_owner_and_saved_value(self):
        memory = {'id': 'owned-memory', 'preferences': {'categories': ['绿茶']}}
        message = '请按已保存的偏好推荐一款商品'
        payload = {'action': 'new_request', 'standalone_question': message,
            'requests': [{'kind': 'recommendation', 'quote': message}],
            'purchase': {'action': 'SEARCH', 'preferred': {'categories': ['绿茶']}, 'evidence': [
                {'field': 'preferred.categories', 'value': '绿茶', 'quote': 'categories: 绿茶',
                 'source': 'MEMORY', 'source_id': 'owned-memory'}]}}
        plan, _, _ = plan_turn(PlanModel(payload), message, [], memory)
        self.assertEqual(plan.purchase.evidence[0].quote, '绿茶')
        payload['purchase']['evidence'][0]['source_id'] = 'foreign-memory'
        with self.assertRaises(ValueError):
            plan_turn(PlanModel(payload), message, [], memory)
        payload['purchase']['evidence'][0]['source_id'] = memory['id']
        memory['preferences']['categories'] = ['白茶']
        with self.assertRaises(ValueError):
            plan_turn(PlanModel(payload), message, [], memory)

    def test_exact_saved_preference_request_uses_only_server_owned_memory(self):
        message = '推荐我偏好的商品'
        model = PlanModel(None)
        plan, source, _ = plan_turn(model, message, [],
            {'id': 'owned', 'preferences': {'categories': ['红茶']}})
        self.assertEqual(source, 'rules')
        self.assertEqual(plan.standalone_question, message)
        self.assertFalse(plan.purchase.required.categories)
        self.assertFalse(model.calls)
        empty, source, _ = plan_turn(model, message, [], None)
        self.assertTrue(empty.needs_clarification)
        self.assertEqual(empty.requests[0].kind, 'clarification')
        self.assertFalse(model.calls)

    def test_model_cannot_rewrite_current_request_without_a_historical_source(self):
        message = '请按已保存的偏好推荐一款商品'
        payload = {'action': 'new_request', 'standalone_question': message + '（红茶）',
            'requests': [{'kind': 'recommendation', 'quote': message}], 'purchase': {'action': 'SEARCH'}}
        with self.assertRaisesRegex(ValueError, 'historical source'):
            plan_turn(PlanModel(payload), message, [], None)
