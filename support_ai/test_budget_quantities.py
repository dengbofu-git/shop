"""Budget-sized quantities with exact cents and bounded search work."""
from unittest import TestCase

from .budget_combinations import Candidate, search_bundles, MAX_NODES, _bounded_pair


class QuantityBudgetTests(TestCase):
    def test_bounded_pair_matches_small_exhaustive_integer_solutions(self):
        for one in range(1, 7):
            for two in range(1, 7):
                first = Candidate(1, 1, '绿茶', one, 6)
                second = Candidate(2, 2, '白茶', two, 5)
                for target in range(1, 65):
                    expected = [(x, y) for x in range(1, 7) for y in range(1, 6) if one*x + two*y == target]
                    actual = _bounded_pair(first, second, target)
                    self.assertEqual(actual is None, not expected)
                    if actual:
                        self.assertIn(actual, expected)
                        self.assertEqual(sum(actual), min(map(sum, expected)))

    def candidates(self):
        return [Candidate(23, 23, '绿茶', 7500, 998, 3), Candidate(130, 130, '白茶', 6600, 143, 3)]

    def test_preferred_tea_types_can_fill_three_thousand_without_five_unit_cap(self):
        result = search_bundles(self.candidates(), budget_cents=300000,
                                categories=['绿茶', '白茶'], preference_max=3, prefer_near=True)
        best = result['plans'][0]
        self.assertEqual(best['subtotal_cents'], 300000)
        self.assertEqual(dict(zip(best['sku_ids'], best['quantities'])), {23: 18, 130: 25})
        self.assertEqual(best['quality_score'], 100)
        self.assertIsNone(result['automatic_quantity_cap'])

    def test_explicit_near_mode_can_use_forty_units_of_a_preferred_product(self):
        result = search_bundles(self.candidates(), budget_cents=300000, preference_max=3, prefer_near=True)
        self.assertEqual(result['plans'][0]['subtotal_cents'], 300000)
        self.assertTrue(any(q > 5 for q in result['plans'][0]['quantities']))

    def test_stock_limits_are_respected_even_when_budget_is_larger(self):
        candidates = [Candidate(c.sku_id, c.product_id, c.category, c.price_cents, 5, 3) for c in self.candidates()]
        best = search_bundles(candidates, budget_cents=300000, categories=['绿茶', '白茶'], preference_max=3, prefer_near=True)['plans'][0]
        self.assertEqual(best['subtotal_cents'], 70500)
        self.assertEqual(best['quantities'], [5, 5])

    def test_explicit_fixed_quantity_is_never_increased_to_fill_budget(self):
        plans = search_bundles(self.candidates(), budget_cents=300000, quantity=3,
                               categories=['绿茶', '白茶'], preference_max=3, prefer_near=True)['plans']
        self.assertTrue(plans)
        self.assertTrue(all(plan['quantities'] == [3, 3] for plan in plans))

    def test_millions_of_units_do_not_require_millions_of_iterations(self):
        result = search_bundles([Candidate(1, 1, '绿茶', 1, 20000000)], budget_cents=10000000, prefer_near=True)
        self.assertEqual(result['plans'][0]['quantities'], [10000000])
        self.assertEqual(result['plans'][0]['subtotal_cents'], 10000000)
        self.assertLess(result['nodes'], MAX_NODES)
        self.assertFalse(result['search_complete'])

    def test_same_product_specifications_do_not_form_two_distinct_products(self):
        candidates = [Candidate(1, 1, '绿茶', 7500, 100), Candidate(2, 1, '绿茶', 6600, 100)]
        self.assertEqual(search_bundles(candidates, budget_cents=300000, distinct_count=2)['plans'], [])

    def test_coprime_pair_search_does_not_overspend_to_make_exact_money(self):
        result = search_bundles(self.candidates(), budget_cents=299999,
                                categories=['绿茶', '白茶'], preference_max=3, prefer_near=True)
        self.assertEqual(result['plans'][0]['subtotal_cents'], 299700)
        self.assertTrue(all(plan['subtotal_cents'] <= 299999 for plan in result['plans']))
