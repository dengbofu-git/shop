"""真实CP-SAT求解与整数穷举交叉校验，无模型或业务库依赖。"""
from itertools import product
from unittest import TestCase
from .budget_combinations import Candidate
from .bundle_optimizer import optimize_bundles

class CpSatBundleTests(TestCase):
    def score(self, rows, qs, budget, prefmax):
        chosen=[(c,q) for c,q in zip(rows,qs) if q]
        cost=sum(c.price_cents*q for c,q in chosen)
        match=sum(1000+(min(1000,c.preference_score*1000//prefmax) if prefmax else 1000) for c,q in chosen)
        repeat=sum(r for c,q in chosen for t,r in [(2,100),(4,50),(8,25),(16,12),(32,6)] if q>=t)
        median=sorted(c.price_cents for c in rows)[len(rows)//2]
        reference=max(1,budget//median)
        return match+repeat+1000*len({c.category for c,q in chosen})+cost*10000//budget-max(c.price_cents*q for c,q in chosen)*3000//budget-sum(qs)*2000//reference

    def test_small_problem_matches_exhaustive_objective(self):
        rows=[Candidate(1,1,'绿茶',110,3,3),Candidate(2,2,'白茶',170,3,2),
              Candidate(3,3,'红茶',230,3,0),Candidate(4,1,'绿茶',130,3,3)]
        for near in (False,True):
            feasible=[]
            for qs in product(range(4),repeat=4):
                selected=[c for c,q in zip(rows,qs) if q]
                total=sum(c.price_cents*q for c,q in zip(rows,qs))
                if not selected or total>1000 or len({c.product_id for c in selected})!=len(selected):continue
                feasible.append((total,self.score(rows,qs,1000,3)))
            result=optimize_bundles(rows,budget_cents=1000,preference_max=3,prefer_near=near)
            best=result['plans'][0]
            target=max(feasible) if near else max(s for total,s in feasible)
            self.assertEqual((best['subtotal_cents'],int(best['objective_value'])) if near else int(best['objective_value']),target)
            self.assertEqual(best['solver_status'],'OPTIMAL')

    def test_budget_recipe_is_not_cheapest_single_unit(self):
        rows=[Candidate(i,i,'茶'+str(i%2),p,500) for i,p in enumerate([740,900,7500,6600],1)]
        result=optimize_bundles(rows,budget_cents=300000)
        plan=result['plans'][0]
        self.assertGreaterEqual(len(plan['sku_ids']),2)
        self.assertGreater(plan['subtotal_cents'],240000)
        self.assertLess(max(plan['quantities']),100)
        self.assertFalse(result['globally_optimal'])

    def test_fixed_quantity_spu_stock_and_categories_are_hard(self):
        rows=[Candidate(1,1,'绿茶',100,5),Candidate(2,1,'绿茶',120,9),Candidate(3,2,'白茶',200,3)]
        result=optimize_bundles(rows,budget_cents=1000,quantity=2,categories=['绿茶','白茶'],distinct_count=2)
        for p in result['plans']:
            self.assertEqual(p['quantities'],[2,2]); self.assertEqual(len(p['sku_ids']),2)
            self.assertLessEqual(p['subtotal_cents'],1000)
        self.assertTrue(result['plans'])

    def test_infeasible_is_reported_without_relaxing_budget(self):
        result=optimize_bundles([Candidate(1,1,'绿茶',200,1)],budget_cents=100,minimum_distinct=2)
        self.assertEqual(result['plans'],[])
        self.assertEqual(result['termination_status'],'INFEASIBLE')

    def test_alternatives_change_product_set(self):
        result=optimize_bundles([Candidate(i,i,'茶',100*i,10) for i in range(1,6)],budget_cents=1000)
        sets=[frozenset(p['sku_ids']) for p in result['plans']]
        self.assertEqual(len(sets),len(set(sets)));self.assertGreater(len(sets),1)

    def test_large_quantities_and_exact_budget(self):
        result=optimize_bundles([Candidate(1,1,'茶',1,20000000)],budget_cents=10000000,
                                minimum_cents=10000000,prefer_near=True)
        self.assertEqual(result['plans'][0]['quantities'],[10000000])

    def test_time_limit_without_solution_does_not_claim_infeasible(self):
        from unittest.mock import patch
        with patch('support_ai.bundle_optimizer.MAX_SECONDS',0):
            result=optimize_bundles([Candidate(1,1,'茶',1,2)],budget_cents=2)
        self.assertEqual(result['plans'],[])
        self.assertEqual(result['termination_status'],'UNKNOWN')
