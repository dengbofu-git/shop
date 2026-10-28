"""Offline regressions for real buyer wording; no DB or remote model required."""
from unittest import TestCase
from unittest.mock import Mock

from .contracts import validate_recommendation_branch, validate_recommendation_intent, RecommendationIntent, budget_scope_reply
from .planning import build_plan
from .recommendation_presentation import budget_scope_question
from .semantic_planning import plan_turn, response_state
from .total_budget_intent import simple_money_intent, simple_total_intent


class ColloquialBudgetTests(TestCase):
    def setUp(self):
        self.model = Mock()
        self.model.with_structured_output.side_effect = AssertionError('Unexpected remote-model path')

    def planned(self, text, history=None):
        semantic, source, previous = plan_turn(self.model, text, history or [], None)
        self.assertEqual(source, 'rules')
        self.model.with_structured_output.assert_not_called()
        plan = build_plan(semantic.requests, source, text, purchase=semantic.purchase)
        purchase = validate_recommendation_branch(semantic.purchase, tool=plan.steps[0].tool)
        return semantic, previous, plan, purchase

    def pending_history(self, text):
        semantic, previous, plan, purchase = self.planned(text)
        snapshot = response_state(semantic, {'product_intent': purchase.model_dump(),
            'task_plan': plan.model_dump(), 'tasks': [
                {'tool': plan.steps[0].tool, 'status': 'needs_clarification'}]}, previous)
        for item in snapshot['purchase']['evidence']:
            item.update(source='CONTEXT', source_id='turn-1')
        return [{'turn_id': 'turn-1', 'user_text': text, 'dialogue_state': snapshot}]

    def test_screenshot_keeps_amount_and_only_asks_scope(self):
        _, _, plan, purchase = self.planned('推荐400块左右的茶')
        self.assertEqual(plan.steps[0].tool, 'recommend_products')
        self.assertEqual(purchase.missing_fields, ['budget_scope'])
        self.assertEqual(purchase.required.price_max, '400.00')
        self.assertEqual(purchase.required.currency, 'CNY')
        self.assertEqual(budget_scope_question(purchase), '您说的人民币400，是每件商品的预算，还是整套商品的总预算？')

    def test_money_aliases_are_not_product_counts(self):
        for alias in ('块', '块钱', '元', '元钱', '人民币', 'CNY'):
            with self.subTest(alias=alias):
                _, _, _, purchase = self.planned('推荐400{}左右的红茶'.format(alias))
                self.assertEqual(purchase.required.categories, ['红茶'])
                self.assertEqual(purchase.missing_fields, ['budget_scope'])

    def test_total_reply_uses_same_amount_without_second_scope_question(self):
        history = self.pending_history('推荐400块左右的红茶')
        for reply in ('总价', '整套预算', '总预算', '套餐', '整套', '整套的总预算', '整套商品的总预算', '按整套计算', '套餐！'):
            with self.subTest(reply=reply):
                semantic, _, plan, purchase = self.planned(reply, history)
                self.assertEqual(semantic.action, 'supplement')
                self.assertEqual(plan.steps[0].tool, 'recommend_bundle')
                self.assertEqual(purchase.action, 'SEARCH')
                self.assertEqual(purchase.missing_fields, [])
                self.assertEqual(purchase.required.budget_max, '400.00')
                self.assertEqual(purchase.required.budget_mode, 'near')
                self.assertEqual(purchase.required.categories, ['红茶'])
                self.assertIsNone(purchase.required.price_max)

    def test_unit_reply_does_not_keep_bundle_mode(self):
        history = self.pending_history('推荐400块左右的红茶')
        for reply in ('单价', '单件预算', '每件商品的预算'):
            with self.subTest(reply=reply):
                _, _, plan, purchase = self.planned(reply, history)
                self.assertEqual(plan.steps[0].tool, 'recommend_products')
                self.assertEqual(purchase.action, 'SEARCH')
                self.assertEqual(purchase.required.price_max, '400.00')
                self.assertIsNone(purchase.required.budget_max)
                self.assertIsNone(purchase.required.budget_mode)
                self.assertEqual(purchase.required.categories, ['红茶'])

    def test_explicit_total_money_does_not_need_scope_clarification(self):
        for alias in ('块', '块钱', '元钱'):
            with self.subTest(alias=alias):
                _, _, plan, purchase = self.planned('推荐总价400{}左右的红茶'.format(alias))
                self.assertEqual(plan.steps[0].tool, 'recommend_bundle')
                self.assertEqual(purchase.required.budget_max, '400.00')
                self.assertEqual(purchase.required.currency, 'CNY')
                self.assertEqual(purchase.action, 'SEARCH')

    def test_explicit_total_generic_tea_scope_reaches_bundle_without_model(self):
        for noun in ('茶', '茶叶', '茶品', '商品', '红茶', '套餐', '茶叶套餐', '红茶套餐'):
            for suffix in ('', '左右'):
                with self.subTest(noun=noun, suffix=suffix):
                    _, _, plan, purchase = self.planned('推荐总价为3000块{}的{}'.format(suffix, noun))
                    self.assertEqual(plan.steps[0].tool, 'recommend_bundle')
                    self.assertEqual(purchase.required.budget_max, '3000.00')
                    self.assertEqual(purchase.required.currency, 'CNY')
                    self.assertEqual(purchase.action, 'SEARCH')
                    self.assertEqual(purchase.missing_fields, [])

    def test_generic_tea_scope_does_not_swallow_other_constraints(self):
        for text in ('推荐总价为3000块的茶，不要红茶', '推荐总价为3000块的有机茶',
                     '推荐总价为3000块的茶饼', '不要推荐总价为3000块的茶', '推荐单价3000块的茶'):
            with self.subTest(text=text):
                self.assertIsNone(simple_total_intent(text))

    def test_scope_choice_does_not_discard_extra_or_negative_requirements(self):
        for text in ('不要按整套', '不是整套，是单件', '套餐，要白茶', '整套，每款两件', '整套订单退款'):
            with self.subTest(text=text):
                self.assertIsNone(budget_scope_reply(text))

    def test_bare_package_without_pending_question_does_not_revive_a_budget(self):
        with self.assertRaisesRegex(AssertionError, 'Unexpected remote-model path'):
            plan_turn(self.model, '套餐', [], None)

    def test_unknown_qualifiers_and_physical_piece_counts_are_not_dropped(self):
        for text in ('推荐400块茶饼', '推荐400块左右的茶，不要红茶',
                     '推荐400块左右的茶，每款3件', '推荐400美元左右的茶'):
            with self.subTest(text=text):
                self.assertIsNone(simple_money_intent(text))

    def test_forged_currency_evidence_is_still_rejected(self):
        text = '推荐400日元左右的茶'
        intent = RecommendationIntent(action='CLARIFY', required={'currency': 'CNY'},
            evidence=[dict(field='required.currency', value='CNY', source='CURRENT', quote='日元')],
            missing_fields=['budget_scope'])
        with self.assertRaises(ValueError):
            validate_recommendation_intent(intent, text, [], None, branch_rules=False)

    def test_new_budget_request_does_not_reuse_previous_total_scope(self):
        _, _, _, old = self.planned('推荐总价200块左右的红茶')
        snapshot = {'version': '1.0', 'status': 'completed', 'task': 'recommendation', 'purchase': old.model_dump()}
        _, _, plan, purchase = self.planned('推荐400块左右的茶', [
            {'turn_id': 'turn-1', 'user_text': '推荐总价200块左右的红茶', 'dialogue_state': snapshot}])
        self.assertEqual(plan.steps[0].tool, 'recommend_products')
        self.assertEqual(purchase.missing_fields, ['budget_scope'])
        self.assertEqual(purchase.required.price_max, '400.00')
        self.assertIsNone(purchase.required.budget_max)
