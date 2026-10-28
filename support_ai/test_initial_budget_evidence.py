"""First-turn evidence failures recover without rewriting purchase filters."""
from unittest import TestCase

from langchain_core.runnables import Runnable, RunnableLambda

from .condition_evidence import PurchaseEvidenceRepair
from .contracts import RecommendationIntent
from .semantic_planning import SemanticPlan, plan_turn


class EvidenceModel(Runnable):
    def __init__(self, purchase, repair=None):
        self.purchase, self.repair, self.calls = purchase, repair, []
    def invoke(self, prompt, config=None, **kwargs):
        raise AssertionError('Unexpected free text')
    def with_structured_output(self, schema):
        def invoke(prompt):
            self.calls.append(schema.__name__)
            if schema is SemanticPlan:
                message = prompt.to_messages()[-1].content.split('本轮原话：')[1].split('\n')[0]
                return SemanticPlan(action='new_request', standalone_question=message,
                    requests=[dict(kind='recommendation', quote=message)], purchase=self.purchase)
            if schema is PurchaseEvidenceRepair:
                return self.repair
            raise AssertionError(schema.__name__)
        return RunnableLambda(invoke)


def purchase(basis='unknown', currency_proof=True):
    return RecommendationIntent(action='CLARIFY', required={'price_basis': basis, 'price_max': '3000.00', 'currency': 'CNY'},
        missing_fields=['budget_scope'], evidence=[
            dict(field='required.price_max', value='3000', source='CURRENT', quote='3000')
        ] + ([dict(field='required.currency', value='CNY', source='CURRENT', quote='块')] if currency_proof else []))


class InitialBudgetEvidenceTests(TestCase):
    message = '给出3000块的茶叶推荐'

    def test_unknown_scope_is_not_an_affirmative_fact_needing_a_quote(self):
        model = EvidenceModel(purchase())
        semantic, _, _ = plan_turn(model, self.message, [], None)
        self.assertEqual(semantic.purchase.required.price_max, '3000.00')
        self.assertEqual(semantic.purchase.required.price_basis, 'unknown')
        self.assertEqual(semantic.purchase.missing_fields, ['budget_scope'])
        self.assertEqual(model.calls, ['SemanticPlan'])

    def test_one_missing_currency_quote_can_be_repaired_without_changing_amount(self):
        model = EvidenceModel(purchase(currency_proof=False), {'evidence': [
            dict(field='required.currency', value='CNY', source='CURRENT', quote='块')]})
        semantic, _, _ = plan_turn(model, self.message, [], None)
        self.assertEqual(semantic.purchase.required.price_max, '3000.00')
        self.assertEqual(semantic.purchase.required.currency, 'CNY')
        self.assertEqual(model.calls, ['SemanticPlan', 'PurchaseEvidenceRepair'])

    def test_unproven_guessed_scope_becomes_a_specific_pending_choice(self):
        model = EvidenceModel(purchase(basis='unit'), {'evidence': [], 'unresolved_scope': True})
        semantic, _, _ = plan_turn(model, self.message, [], None)
        self.assertEqual(semantic.purchase.required.price_basis, 'unknown')
        self.assertEqual(semantic.purchase.required.price_max, '3000.00')
        self.assertIn('budget_scope', semantic.purchase.missing_fields)

    def test_repair_cannot_silently_replace_a_filter_with_different_money(self):
        model = EvidenceModel(purchase(currency_proof=False), {'evidence': [
            dict(field='required.price_max', value='1', source='CURRENT', quote='1')]})
        with self.assertRaises(RuntimeError):
            plan_turn(model, self.message, [], None)
        self.assertEqual(model.purchase.required.price_max, '3000.00')

    def test_unresolved_total_amount_is_preserved_for_later_scope_choice(self):
        raw = purchase()
        raw.required.price_max = None
        raw.required.budget_max = '3000.00'
        raw.evidence[0].field = 'required.budget_max'
        semantic, _, _ = plan_turn(EvidenceModel(raw), self.message, [], None)
        self.assertEqual(semantic.purchase.required.price_max, '3000.00')
        self.assertIsNone(semantic.purchase.required.budget_max)

    def test_captured_synthetic_default_cap_does_not_block_scope_correction(self):
        raw = purchase(basis='total')
        raw.required.categories = ['茶叶']
        raw.required.budget_mode = 'cap'
        raw.evidence += [dict(field='required.categories', value='茶叶', source='CURRENT', quote='茶叶'),
                         dict(field='required.budget_mode', value='cap', source='CURRENT', quote='3000元预算'),
                         dict(field='required.price_basis', value='total', source='CURRENT', quote='3000元预算')]
        # Validate dict evidence in the same way the model adapter does.
        raw = RecommendationIntent.model_validate(raw.model_dump())
        raw.evidence[1].quote = '元'
        model = EvidenceModel(raw, {'evidence': [], 'unresolved_scope': True})
        semantic, _, _ = plan_turn(model, '我想买点茶叶，3000元预算，帮我选选', [], None)
        self.assertEqual(semantic.purchase.required.price_max, '3000.00')
        self.assertEqual(semantic.purchase.required.categories, [])
        self.assertIsNone(semantic.purchase.required.budget_mode)
        self.assertEqual(semantic.purchase.missing_fields, ['budget_scope'])

    def test_a_single_explicit_budget_omitted_by_model_is_preserved(self):
        for message in ('茶叶推荐一下，金额3000元', '给出3000块的茶叶推荐', '帮我看看3000块能选哪些茶叶'):
            model = EvidenceModel(RecommendationIntent(action='SEARCH'))
            semantic, _, _ = plan_turn(model, message, [], None)
            self.assertEqual(semantic.purchase.required.price_max, '3000.00')
            self.assertEqual(semantic.purchase.required.price_basis, 'unknown')
            self.assertEqual(semantic.purchase.missing_fields, ['budget_scope'])

    def test_money_guard_does_not_invent_scope_from_ambiguous_or_old_numbers(self):
        from .initial_purchase import reconcile_initial_purchase
        for message in ('以前预算3000元，今天推荐茶叶', '预算3000元到4000元', '预算至少3000元', '每件金额3000元'):
            result = reconcile_initial_purchase(RecommendationIntent(action='SEARCH'), message)
            self.assertIsNone(result.required.price_max)

    def test_explicit_cap_and_exact_mode_are_not_removed(self):
        from .initial_purchase import reconcile_initial_purchase
        raw = purchase()
        for mode, message in (('cap', '预算不超过3000元'), ('exact', '正好3000元')):
            raw.required.budget_mode = mode
            self.assertEqual(reconcile_initial_purchase(raw, message).required.budget_mode, mode)

    def test_normalization_cannot_hide_forged_memory_or_context_provenance(self):
        for source in ('MEMORY', 'CONTEXT'):
            raw = purchase()
            raw.required.categories = ['茶叶']
            raw.evidence.append(dict(field='required.categories', value='茶叶', source=source, source_id='foreign', quote='茶叶'))
            raw = RecommendationIntent.model_validate(raw.model_dump())
            with self.assertRaises(ValueError):
                plan_turn(EvidenceModel(raw), self.message, [], None)
