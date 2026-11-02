"""Synthetic catalog -> real candidate selection -> real CP-SAT priority."""
from django.test import TestCase
from goods.models import Catalog, SPU, SKU
from users.models import UserProfile
from .contracts import RecommendationIntent
from .bundle_recommendations import recommend_bundle


class BundlePriorityTests(TestCase):
    def setUp(self):
        merchant=UserProfile.objects.create(username='priority-seller',user_type='merchant',is_active=True)
        self.ids=[]
        for category,price in [('绿茶',10),('白茶',99)]:
            spu=SPU.objects.create(name='合成'+category,catalog=Catalog.objects.create(name=category),merchant=merchant)
            self.ids.append(SKU.objects.create(spu=spu,name='合成规格',caption='',price=price,
                cost_price=1,market_price=price,stock=1).pk)

    def test_default_and_near_priorities_survive_catalog_tool_projection(self):
        for mode,index in [('cap',0),('near',1)]:
            intent=RecommendationIntent(action='SEARCH',required={'price_basis':'total','budget_max':'100',
                'currency':'CNY','composition':'single','budget_mode':mode},preferred={'categories':['绿茶']})
            result=recommend_bundle(intent)
            self.assertEqual(result['recommendation_status'],'MATCHED')
            primary=result['recommendation_bundles'][0]
            self.assertEqual(primary['items'][0]['sku_id'],self.ids[index])
            self.assertLessEqual(float(primary['subtotal']),100)
            self.assertEqual(result['bundle_search']['policy_version'],'match-first-cpsat-v2')
