"""Checkout limits use the actual selection before touching stock or cart state."""
import json
import os
import uuid
from unittest import skipUnless
from unittest.mock import patch

from django.test import TestCase, override_settings
from redis import Redis
from carts.state import SNAPSHOT_SCRIPT

from goods.models import SKU
from inventory.models import Inventory
from inventory.services import InventoryService
from .models import CartCleanupTask, CheckoutRequest, OrderGoods, OrderInfo, StockHold
from .reservations import ReservationError
from .test_reservations import Fixtures


class LimitFixtures(Fixtures):
    def seed_limit(self, total):
        self.seed()
        self.products = [self.skus[0]]
        for i in range(1, total):
            self.products.append(SKU.objects.create(
                spu=self.skus[0].spu, name='Limit %s'%i, price=10, market_price=12,
                cost_price=5, stock=100, is_launched=True))

    def quantities(self, count=1):
        return {sku.pk:count for sku in self.products}


class CheckoutLimitServiceTests(LimitFixtures, TestCase):
    def setUp(self):
        self.seed_limit(21)

    def test_twenty_sku_rows_allow_more_than_twenty_total_units(self):
        orders = self.place(items={sku.pk:10 for sku in self.products[:20]})
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].total_count, 200)
        self.assertEqual((OrderGoods.objects.count(), StockHold.objects.count()), (20, 20))

    def test_twenty_one_is_rejected_before_expiry_and_stock_locks(self):
        with patch('orders.reservations.expire_orders') as expire, patch.object(
                InventoryService, 'locked_ledgers', wraps=InventoryService.locked_ledgers) as lock:
            with self.assertRaises(ReservationError) as caught:
                self.place(items=self.quantities())
        self.assertEqual(caught.exception.code, 'CHECKOUT_SKU_LIMIT')
        self.assertEqual(caught.exception.message, '单次最多结算20种商品，请减少勾选数量后分批结算')
        self.assertEqual(caught.exception.details['checkout_sku_limit'], 20)
        expire.assert_not_called()
        lock.assert_not_called()
        self.assertEqual((OrderInfo.objects.count(), StockHold.objects.count(), CheckoutRequest.objects.count()), (0,0,0))
        self.assertFalse(Inventory.objects.exists())

    @override_settings(RESERVATION_MAX_SKUS_PER_CHECKOUT=2)
    def test_configured_limit_is_enforced_by_the_service(self):
        with self.assertRaises(ReservationError) as caught:
            self.place(items={sku.pk:1 for sku in self.products[:3]})
        self.assertEqual(caught.exception.details['checkout_sku_limit'], 2)
        self.assertEqual(caught.exception.message, '单次最多结算2种商品，请减少勾选数量后分批结算')

    def test_normalized_duplicate_sku_is_not_silently_merged(self):
        sid=self.products[0].pk
        with self.assertRaises(ReservationError) as caught:
            self.place(items={sid:1,str(sid):2})
        self.assertEqual(caught.exception.code, 'INVALID_CART')
        self.assertFalse(OrderInfo.objects.exists())

    @override_settings(RESERVATION_MAX_UNPAID_AMOUNT=1)
    def test_amount_rejection_happens_before_ledger_initialization(self):
        with patch.object(InventoryService, 'locked_ledgers', wraps=InventoryService.locked_ledgers) as lock:
            with self.assertRaises(ReservationError) as caught:
                self.place(items={self.products[0].pk:1})
        self.assertEqual(caught.exception.code, 'UNPAID_AMOUNT_LIMIT')
        lock.assert_not_called()
        self.assertFalse(Inventory.objects.exists())


@skipUnless(os.environ.get('CART_TEST_REDIS_URL'), 'Requires explicitly isolated Redis')
class CheckoutLimitApiTests(LimitFixtures, TestCase):
    def setUp(self):
        self.seed_limit(21)
        self.redis=Redis.from_url(os.environ['CART_TEST_REDIS_URL'])
        self.key='carts_'+self.buyers[0].username
        self.redis.delete(self.key)
        self.addCleanup(self.redis.close)
        self.addCleanup(self.redis.delete,self.key)
        for name in ('orders.views.get_redis_connection','carts.views.get_redis_connection'):
            mock=patch(name,return_value=self.redis);mock.start();self.addCleanup(mock.stop)
        self.url='/v1/orders/'+self.buyers[0].username

    def cart(self, selected=21):
        self.redis.hset(self.key,mapping={str(sku.pk):json.dumps({'count':1,'status':i<selected})
                                       for i,sku in enumerate(self.products)})

    def post(self, **extra):
        payload={'settlement_type':'0','address_id':self.addresses[0].pk,'request_id':uuid.uuid4().hex,**extra}
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url,payload,content_type='application/json',**self.headers(self.buyers[0]))

    def assert_limit_rejected(self,response,limit=20):
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()['error_code'],'CHECKOUT_SKU_LIMIT')
        self.assertEqual(response.json()['checkout_sku_limit'],limit)
        self.assertFalse(OrderInfo.objects.exists())
        self.assertFalse(StockHold.objects.exists())

    def test_missing_null_or_empty_sku_list_cannot_bypass_real_selected_count(self):
        self.cart()
        before=self.redis.hgetall(self.key)
        for extra in ({},{'sku_list':None},{'sku_list':[]}):
            with self.subTest(extra=extra):
                self.assert_limit_rejected(self.post(**extra))
                self.assertEqual(self.redis.hgetall(self.key),before)
        self.assertFalse(CartCleanupTask.objects.exists())
        self.assertFalse(CheckoutRequest.objects.exists())

    def test_explicit_twenty_one_and_forged_quantities_are_rejected(self):
        self.cart()
        before=self.redis.hgetall(self.key)
        rows=[{'id':sku.pk,'count':0,'price':0} for sku in self.products]
        self.assert_limit_rejected(self.post(sku_list=rows))
        self.assertEqual(self.redis.hgetall(self.key),before)

    def test_twenty_selected_of_twenty_one_is_allowed_and_unselected_row_remains(self):
        self.cart(selected=20)
        response=self.post()
        self.assertEqual(response.status_code,200)
        self.assertEqual(OrderGoods.objects.count(),20)
        self.assertEqual(self.redis.hlen(self.key),1)
        self.assertFalse(json.loads(self.redis.hget(self.key,self.products[-1].pk))['status'])

    def test_explicit_subset_counts_only_actual_requested_selected_rows(self):
        self.cart()
        response=self.post(sku_list=[{'id':sku.pk} for sku in self.products[:20]])
        self.assertEqual(response.status_code,200)
        self.assertEqual(OrderGoods.objects.count(),20)
        self.assertEqual(self.redis.hlen(self.key),1)

    def test_duplicate_sku_request_keeps_its_rejection_contract(self):
        self.cart(selected=1)
        sid=self.products[0].pk
        response=self.post(sku_list=[{'id':sid},{'id':str(sid)}])
        self.assertEqual(response.status_code,400)
        self.assertEqual(response.json()['error_code'],'INVALID_CART')
        self.assertFalse(OrderInfo.objects.exists())

    def test_over_limit_does_not_drain_existing_cleanup_or_upgrade_legacy_rows(self):
        self.cart()
        sid=self.products[0].pk
        self.redis.hset(self.key,sid,json.dumps({'count':2,'status':True,'generation':'old-task','version':1,'added':2,'removed':0}))
        prior=CheckoutRequest.objects.create(user=self.buyers[0],request_id=uuid.uuid4().hex,fingerprint='previous')
        task=CartCleanupTask.objects.create(checkout=prior,sku_id=sid,generation='old-task',version=1,consumed_from=0,consumed_to=1)
        before=self.redis.hgetall(self.key)
        self.assert_limit_rejected(self.post())
        task.refresh_from_db()
        self.assertEqual((task.status,task.attempts),('pending',0))
        self.assertEqual(self.redis.hgetall(self.key),before)
        self.assertEqual(CheckoutRequest.objects.count(),1)

    def test_preview_applies_the_same_limit_without_modifying_cart(self):
        self.cart()
        before=self.redis.hgetall(self.key)
        response=self.client.get(self.url+'/advance?settlement_type=0',**self.headers(self.buyers[0]))
        self.assert_limit_rejected(response)
        self.assertEqual(self.redis.hgetall(self.key),before)

    def test_selection_growing_during_snapshot_is_rejected_without_legacy_upgrade(self):
        self.cart(selected=20)
        sid=self.products[-1].pk
        before=self.redis.hgetall(self.key)
        concurrent=json.dumps({'count':1,'status':True})
        original=self.redis.eval
        def select_another(script,*args):
            if script==SNAPSHOT_SCRIPT:
                self.redis.hset(self.key,sid,concurrent)
            return original(script,*args)
        with patch.object(self.redis,'eval',side_effect=select_another):
            self.assert_limit_rejected(self.post())
        before[str(sid).encode()]=concurrent.encode()
        self.assertEqual(self.redis.hgetall(self.key),before)
        self.assertFalse(CartCleanupTask.objects.exists())

    @override_settings(RESERVATION_MAX_SKUS_PER_CHECKOUT=2)
    def test_preview_publishes_real_config_and_direct_buy_is_one_sku(self):
        self.cart(selected=1)
        response=self.client.get(self.url+'/advance?settlement_type=0',**self.headers(self.buyers[0]))
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['data']['checkout_sku_limit'],2)
        self.assertEqual(response.json()['data']['reservation_ttl_seconds'],900)
        response=self.post(settlement_type='1',sku_id=self.products[0].pk,buy_count=21)
        self.assertEqual(response.status_code,200)
        self.assertEqual(OrderGoods.objects.get().count,21)
