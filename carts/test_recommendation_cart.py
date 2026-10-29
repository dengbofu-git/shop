"""隔离SQLite + 明确指定的临时Redis；不使用业务Redis。"""
import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from unittest.mock import patch
from django.test import TestCase
from django.utils import timezone
from redis import Redis
from goods.models import Catalog, SPU, SKU
from users.models import UserProfile
from tea_saas.utils import jwt_encode
from support_ai.models import SupportConversation, SupportTurn
from support_ai.recommendations import available_products
from inventory.models import Warehouse, Inventory
from .atomic_add import add_items, request_hash, CartError


@skipUnless(os.environ.get('CART_TEST_REDIS_URL'), '需要本次独立临时Redis的显式URL')
class RecommendationCartTests(TestCase):
    def setUp(self):
        self.redis = Redis.from_url(os.environ['CART_TEST_REDIS_URL'])
        self.prefix = 'ct' + uuid.uuid4().hex[:6]
        self.buyer = UserProfile.objects.create(username=self.prefix, user_type='customer', is_active=True)
        self.other = UserProfile.objects.create(username=self.prefix+'o', user_type='customer', is_active=True)
        self.merchant = UserProfile.objects.create(username=self.prefix+'s', user_type='merchant', is_active=True)
        self.category = Catalog.objects.create(name='红茶')
        self.skus = []
        for i in range(2):
            spu = SPU.objects.create(name='合成茶'+str(i), catalog=self.category, merchant=self.merchant)
            self.skus.append(SKU.objects.create(spu=spu, name='合成规格', price='10.00', market_price='10', cost_price='1', stock=100, is_launched=True))
        self.request_id = uuid.uuid4()
        self.conversation = SupportConversation.objects.create(user=self.buyer, revision=1)
        cards = [{'sku_id':s.pk, 'price':'10.00', 'currency':'CNY', 'quantity':i+2} for i,s in enumerate(self.skus)]
        self.bundle_id='bundle-aaaaaaaaaaaa'
        self.turn=SupportTurn.objects.create(user=self.buyer, conversation=self.conversation,request_id=self.request_id,
            request_hash='synthetic',sequence=1,user_text='合成套餐推荐',answer='合成',intent='recommendation',
            response={'recommendations':cards,'recommendation_bundles':[{'bundle_id':self.bundle_id,'items':cards}]})
        self.url='/v1/carts/'+self.buyer.username+'/recommendations'
        self.headers={'HTTP_AUTHORIZATION':'Bearer '+jwt_encode({'id':self.buyer.pk,'username':self.buyer.username})}
        self.patch=patch('carts.views.get_redis_connection',return_value=self.redis); self.patch.start()
        self.addCleanup(self.patch.stop)

    def tearDown(self):
        keys=list(self.redis.scan_iter(match='cart-add-receipt:'+self.prefix+':*'))
        self.redis.delete('carts_'+self.prefix,*keys)
        self.redis.close()

    def payload(self, **kwargs):
        return {'request_id':str(uuid.uuid4()),'recommendation_request_id':str(self.request_id),'bundle_id':self.bundle_id,**kwargs}

    def submit(self, payload=None, headers=None):
        return self.client.post(self.url,data=json.dumps(payload or self.payload()),content_type='application/json',**(self.headers if headers is None else headers))

    def cart(self):
        return {k.decode():json.loads(v) for k,v in self.redis.hgetall('carts_'+self.prefix).items()}

    def test_whole_bundle_and_retry_add_once(self):
        payload=self.payload();first=self.submit(payload);again=self.submit(payload)
        self.assertEqual(first.status_code,200);self.assertTrue(again.json()['replayed'])
        self.assertEqual([self.cart()[str(s.pk)]['count'] for s in self.skus],[2,3])

    def test_single_card_uses_user_quantity(self):
        payload=self.payload(sku_id=self.skus[0].pk,count=4);payload.pop('bundle_id')
        self.assertEqual(self.submit(payload).status_code,200)
        self.assertEqual(self.cart()[str(self.skus[0].pk)]['count'],4)

    def test_changed_payload_cannot_reuse_operation(self):
        payload=self.payload(sku_id=self.skus[0].pk,count=1)
        self.assertEqual(self.submit(payload).status_code,200)
        payload['count']=2
        self.assertEqual(self.submit(payload).status_code,409)
        self.assertEqual(self.cart()[str(self.skus[0].pk)]['count'],1)

    def test_other_buyer_or_path_cannot_use_record(self):
        other={'HTTP_AUTHORIZATION':'Bearer '+jwt_encode({'id':self.other.pk,'username':self.other.username})}
        self.assertEqual(self.submit(headers=other).status_code,403)
        self.url='/v1/carts/'+self.other.username+'/recommendations'
        self.assertEqual(self.submit(headers=other).status_code,404)
        self.assertEqual(self.cart(),{})

    def test_no_login_cannot_add(self):
        self.assertEqual(self.submit(headers={}).status_code,401)
        self.assertEqual(self.cart(),{})

    def test_deleted_history_cannot_add(self):
        self.conversation.delete()
        self.assertEqual(self.submit().status_code,404)
        self.assertEqual(self.cart(),{})

    def test_forged_item_or_plan_and_whole_count_are_rejected(self):
        for payload in [self.payload(sku_id=999999,count=1),self.payload(bundle_id='bundle-bbbbbbbbbbbb'),self.payload(count=1)]:
            self.assertIn(self.submit(payload).status_code,(400,404))
        self.assertEqual(self.cart(),{})

    def test_downlisted_price_changed_or_inactive_shop_does_not_partially_add(self):
        self.skus[1].is_launched=False;self.skus[1].save()
        self.assertEqual(self.submit().status_code,409);self.assertEqual(self.cart(),{})
        self.skus[1].is_launched=True;self.skus[1].price='12';self.skus[1].save()
        self.assertEqual(self.submit().status_code,409);self.assertEqual(self.cart(),{})
        self.skus[1].price='10';self.skus[1].save();self.merchant.is_active=False;self.merchant.save()
        self.assertEqual(self.submit().status_code,409);self.assertEqual(self.cart(),{})

    def test_existing_count_is_included_and_no_partial_write(self):
        self.redis.hset('carts_'+self.prefix,str(self.skus[1].pk),json.dumps({'count':99,'status':True}))
        self.assertEqual(self.submit().status_code,409)
        self.assertEqual(len(self.cart()),1)
        self.assertEqual(self.cart()[str(self.skus[1].pk)]['count'],99)

    def test_retry_after_price_change_returns_original_receipt(self):
        payload=self.payload();self.assertEqual(self.submit(payload).status_code,200)
        self.skus[1].price='20';self.skus[1].save()
        result=self.submit(payload)
        self.assertEqual(result.status_code,200);self.assertTrue(result.json()['replayed'])
        self.assertEqual(self.cart()[str(self.skus[1].pk)]['count'],3)

    def test_native_lua_concurrent_distinct_and_identical_requests(self):
        items=[{'sku_id':str(self.skus[0].pk),'count':2,'available_stock':100}]
        def write(operation):return add_items(self.redis,self.prefix,operation,'same',items)
        operation=str(uuid.uuid4())
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write,[operation]*8))
        self.assertEqual(self.cart()[str(self.skus[0].pk)]['count'],2)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(write,[str(uuid.uuid4()) for _ in range(8)]))
        self.assertEqual(self.cart()[str(self.skus[0].pk)]['count'],18)

    def test_legacy_single_post_also_blocks_downlisted_and_is_atomic(self):
        url='/v1/carts/'+self.prefix
        s=self.skus[0];s.is_launched=False;s.save()
        self.assertEqual(self.client.post(url,{'sku_id':s.pk,'count':1},content_type='application/json',**self.headers).json()['code'],30101)
        s.is_launched=True;s.save()
        self.assertEqual(self.client.post(url,{'sku_id':s.pk,'count':1},content_type='application/json',**self.headers).status_code,200)

    def test_recommendations_filter_downlisted_zero_stock_disabled_warehouse_and_shop(self):
        first,second=self.skus
        first.is_launched=False;first.save()
        self.assertNotIn(first.pk,available_products().values_list('pk',flat=True))
        warehouse=Warehouse.objects.create(code=self.prefix,name='合成仓',is_active=False)
        Inventory.objects.create(sku=second,warehouse=warehouse,quantity=50,available_quantity=50)
        self.assertNotIn(second.pk,available_products().values_list('pk',flat=True))
        warehouse.is_active=True;warehouse.save()
        self.assertIn(second.pk,available_products().values_list('pk',flat=True))
        self.merchant.is_active=False;self.merchant.save()
        self.assertNotIn(second.pk,available_products().values_list('pk',flat=True))

    def test_unbound_merchant_is_not_orderable_or_recommended(self):
        self.skus[0].spu.merchant=None
        self.skus[0].spu.save()
        self.assertNotIn(self.skus[0].pk,available_products().values_list('pk',flat=True))
        self.assertEqual(self.submit().status_code,409)
        self.assertEqual(self.cart(),{})

    def test_stale_legacy_edit_cannot_overwrite_atomic_add(self):
        from .atomic_add import compare_set
        key='carts_'+self.prefix;sku=str(self.skus[0].pk)
        self.redis.hset(key,sku,json.dumps({'count':1,'status':False}))
        before=self.redis.hget(key,sku)
        add_items(self.redis,self.prefix,str(uuid.uuid4()),'synthetic',
                  [{'sku_id':sku,'count':2,'available_stock':100}])
        self.assertFalse(compare_set(self.redis,key,sku,before,json.dumps({'count':1,'status':True})))
        self.assertEqual(self.cart()[sku]['count'],3)
