"""Deterministic budget arithmetic and bounded-search regression tests."""
from itertools import combinations
from random import Random
from unittest import TestCase
from unittest.mock import patch

from .budget_combinations import Candidate, search_bundles
from .semantic_planning import plan_turn
from .planning import recommendation_tool
from tea_saas.currency import to_base, display


class BudgetCombinationTests(TestCase):
    def test_exact_cap_categories_quantity_and_product_uniqueness(self):
        rows=[Candidate(1,1,'绿茶',6000,2),Candidate(2,2,'白茶',4000,2),
              Candidate(3,1,'绿茶',1000,20),Candidate(4,4,'红茶',10000,0)]
        result=search_bundles(rows,budget_cents=20000,categories=['绿茶','白茶'],quantity=2)
        self.assertEqual(result['plans'][0]['subtotal_cents'],20000)
        self.assertEqual(result['plans'][0]['sku_ids'],[1,2])
        for plan in result['plans']:
            selected=[r for r in rows if r.sku_id in plan['sku_ids']]
            self.assertEqual(len(selected),len({r.product_id for r in selected}))
            self.assertLessEqual(plan['subtotal_cents'],20000)

    def test_exhaustive_small_pools_match_integer_oracle(self):
        rng=Random(22)
        for _ in range(30):
            rows=[Candidate(i,i//2,str(i%3),rng.randrange(1,10000),2) for i in range(1,9)]
            cap=rng.randrange(5000,25000)
            for near in (False, True):
                actual=search_bundles(rows,budget_cents=cap,categories=['1'],quantity=2,prefer_near=near)
                expected=[]
                for size in range(1,5):
                    for selected in combinations(rows,size):
                        total=sum(r.price_cents*2 for r in selected)
                        if total>cap or len({r.product_id for r in selected})!=size or '1' not in {r.category for r in selected}:
                            continue
                        quality=(8000+20*(len({r.category for r in selected})*100//size))//100
                        ids=tuple(r.sku_id for r in selected)
                        rank=(-quality,cap-total,2*size,size,tuple((pk,2) for pk in ids))
                        if near: rank=(0 if total>=(cap*95+99)//100 else 1,)+rank
                        expected.append((rank,ids,total))
                expected.sort()
                self.assertTrue(actual['search_complete'])
                self.assertEqual([(p['sku_ids'],p['subtotal_cents']) for p in actual['plans']],[(list(ids),total) for _,ids,total in expected[:64]])

    def test_hard_floor_exact_count_and_no_solution(self):
        rows=[Candidate(1,1,'绿茶',19500,1),Candidate(2,2,'白茶',1000,1)]
        self.assertEqual(search_bundles(rows,budget_cents=20000,minimum_cents=19000,distinct_count=1)['plans'][0]['sku_ids'],[1])
        self.assertFalse(search_bundles(rows,budget_cents=20000,categories=['绿茶','白茶'])['plans'])

    def test_reject_invalid_bounds_and_duplicate_candidates(self):
        row=Candidate(1,1,'绿茶',100,1)
        for options in ({'budget_cents':0},{'budget_cents':100,'quantity':0},{'budget_cents':100,'distinct_count':5}):
            with self.assertRaises(ValueError):search_bundles([row],**options)
        with self.assertRaises(ValueError):search_bundles([row,row],budget_cents=1000)

    def test_search_limit_is_reported(self):
        rows=[Candidate(i,i,'绿茶',100,1) for i in range(40)]
        with patch('support_ai.budget_combinations.MAX_NODES',10):
            result=search_bundles(rows,budget_cents=1000)
        self.assertFalse(result['search_complete'])

    def test_explicit_foreign_caps_floors_and_default_cny(self):
        self.assertEqual(str(to_base('200','USD')),'1428.57')
        self.assertEqual(str(to_base('200','USD',upper=False)),'1428.58')
        self.assertEqual(str(to_base('200')),'200.00')
        self.assertEqual(str(display('200','USD')),'28.00')

    def test_rule_intents_route_to_bundle_without_model(self):
        for message in ('总价200，推荐绿茶和白茶','总价200元，推荐绿茶和白茶，每款两件','总价200美元，推荐绿茶和白茶'):
            plan,source,_=plan_turn(None,message,[],None)
            self.assertEqual(source,'rules')
            self.assertEqual(plan.purchase.required.price_basis,'total')
            self.assertEqual(recommendation_tool(plan.purchase),'recommend_bundle')
