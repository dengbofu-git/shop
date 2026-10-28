import json
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Barrier
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection,connections,IntegrityError,transaction
from django.test import TestCase,TransactionTestCase,override_settings
from django.utils import timezone
from goods.models import Catalog,SPU,SKU
from users.models import UserProfile,Address
from tea_saas.utils import jwt_encode
from inventory.models import Inventory,Warehouse
from inventory.services import InventoryService
from inventory.availability import available_quantity
from .models import OrderInfo,OrderGoods,StockHold,ReservationPolicy,CheckoutRequest
from .reservations import create_orders,close_order,confirm_payment,ship_order,expire_orders,ReservationError,fingerprint


class Fixtures:
    def seed(self):
        self.buyers=[UserProfile.objects.create(username='holdbuy%s'%i,is_active=True) for i in range(3)]
        self.shops=[UserProfile.objects.create(username='holdshop%s'%i,user_type='merchant',is_active=True) for i in range(2)]
        cat=Catalog.objects.create(name='预留测试茶')
        self.skus=[]
        for i,shop in enumerate(self.shops):
            spu=SPU.objects.create(name='商品%s'%i,catalog=cat,merchant=shop)
            self.skus.append(SKU.objects.create(spu=spu,name='规格%s'%i,price=10,market_price=12,cost_price=5,stock=100,is_launched=True))
            ReservationPolicy.objects.create(merchant=shop,max_stock_percent=100,max_unpaid_quantity=300)
        self.addresses=[Address.objects.create(user_profile=u,receiver='Test',receiver_mobile='12345678901',address='Synthetic',postcode='000000',tag='Test') for u in self.buyers]
    def place(self,buyer=0,items=None,key=None,digest='same',address=None):
        return create_orders(self.buyers[buyer],key or uuid.uuid4().hex,digest,address or self.addresses[buyer].pk,items or {self.skus[0].pk:10},'127.0.0.1')
    def headers(self,user):return {'HTTP_AUTHORIZATION':'Bearer '+jwt_encode({'id':user.pk})}


class ReservationTests(Fixtures,TestCase):
    def setUp(self):self.seed()
    def test_100_stock_first_99_then_50_refused_and_cart_uses_remaining_one(self):
        first=self.place(items={self.skus[0].pk:99})[0]
        with self.assertRaises(ReservationError) as error:self.place(buyer=1,items={self.skus[0].pk:50})
        self.assertEqual(error.exception.code,'INSUFFICIENT_STOCK')
        self.assertEqual(OrderInfo.objects.count(),1)
        self.assertEqual(available_quantity(self.skus[0]),1)
        confirm_payment(first.pk,'trade-99',first.total_amount)
        ship_order(first.pk,self.shops[0]);ship_order(first.pk,self.shops[0])
        inv=Inventory.objects.get(sku=self.skus[0]);self.assertEqual((inv.quantity,inv.reserved_quantity,inv.available_quantity),(1,0,1))
    def test_one_unit_and_direct_overbuy_fail_without_partial_order(self):
        with self.assertRaises(ReservationError):self.place(items={self.skus[0].pk:101})
        self.assertFalse(OrderInfo.objects.exists());self.assertFalse(CheckoutRequest.objects.exists())
    def test_multi_shop_split_and_all_or_nothing_stock(self):
        orders=self.place(items={s.pk:10 for s in self.skus})
        self.assertEqual(len(orders),2)
        for order in orders:self.assertEqual(order.ordergoods_set.count(),1)
        self.assertEqual(len({i.merchant_snapshot_id for i in OrderGoods.objects.all()}),2)
        with self.assertRaises(ReservationError):self.place(buyer=1,items={self.skus[0].pk:1,self.skus[1].pk:101})
        self.assertEqual(OrderInfo.objects.count(),2);self.assertEqual(available_quantity(self.skus[0]),90)
    def test_idempotent_request_is_not_a_renewal_and_different_payload_conflicts(self):
        key=uuid.uuid4().hex;order=self.place(key=key)[0]
        expiry=order.expires_at
        self.assertEqual(self.place(key=key)[0].pk,order.pk)
        self.assertEqual(self.place(key=key)[0].expires_at,expiry)
        with self.assertRaises(ReservationError):self.place(key=key,digest='different')
        self.assertEqual(StockHold.objects.count(),1)
    def test_same_sku_second_request_and_buyer_cumulative_limits(self):
        self.place()
        with self.assertRaises(ReservationError) as err:self.place()
        self.assertEqual(err.exception.code,'SKU_ALREADY_RESERVED')
        with override_settings(RESERVATION_MAX_UNPAID_QUANTITY=15):
            with self.assertRaises(ReservationError):self.place(items={self.skus[1].pk:10})
        with override_settings(RESERVATION_MAX_UNPAID_AMOUNT=150):
            with self.assertRaises(ReservationError):self.place(items={self.skus[1].pk:10})
    def test_cancel_and_expire_release_exactly_once_and_do_not_reset_abuse_history(self):
        order=self.place()[0]
        close_order(order.pk,self.buyers[0].pk);close_order(order.pk,self.buyers[0].pk)
        self.assertEqual(available_quantity(self.skus[0]),100)
        for _ in range(2):
            order=self.place()[0];OrderInfo.objects.filter(pk=order.pk).update(expires_at=timezone.now()-timedelta(seconds=1));expire_orders()
        with self.assertRaises(ReservationError) as err:self.place()
        self.assertEqual(err.exception.code,'RESERVATION_COOLDOWN')
        self.assertEqual(OrderInfo.objects.filter(status=0).count(),3)
    def test_paid_holds_do_not_expire_and_late_payment_records_exception_without_stock(self):
        order=self.place()[0];confirm_payment(order.pk,'paid-1',order.total_amount)
        OrderInfo.objects.filter(pk=order.pk).update(expires_at=timezone.now()-timedelta(days=1))
        expire_orders();self.assertEqual(available_quantity(self.skus[0]),90)
        late=self.place(buyer=1)[0]
        OrderInfo.objects.filter(pk=late.pk).update(expires_at=timezone.now()-timedelta(seconds=1))
        received=confirm_payment(late.pk,'late-1',late.total_amount)
        self.assertEqual((received.status,received.payment_exception),(0,'late_payment_refund_required'))
        self.assertEqual(available_quantity(self.skus[0]),90)
    def test_verified_payment_is_idempotent_and_rejects_wrong_amount(self):
        order=self.place()[0]
        with self.assertRaises(ReservationError):confirm_payment(order.pk,'bad-1',Decimal('1'))
        confirm_payment(order.pk,'good-1',order.total_amount);confirm_payment(order.pk,'good-1',order.total_amount)
        with self.assertRaises(ReservationError):confirm_payment(order.pk,'other-1',order.total_amount)
        self.assertEqual(StockHold.objects.get().state,'paid')
    def test_bulk_threshold_and_policy_are_per_merchant(self):
        ReservationPolicy.objects.filter(merchant=self.shops[0]).update(max_stock_percent=50)
        with self.assertRaises(ReservationError) as err:self.place(items={self.skus[0].pk:99})
        self.assertEqual(err.exception.code,'BULK_CONFIRMATION_REQUIRED')
        self.assertFalse(OrderInfo.objects.exists())
        self.assertEqual(self.place(items={self.skus[1].pk:99})[0].total_count,99)
    def test_merchant_and_legacy_shipping_cannot_consume_another_orders_hold(self):
        self.place(items={self.skus[0].pk:99})
        with self.assertRaises(ValueError):InventoryService.ship_deduct_sku(self.skus[0].pk,50,'legacy')
        with self.assertRaises(ValueError):InventoryService.adjust_stock(self.skus[0].pk,50)
        inv=Inventory.objects.get(sku=self.skus[0]);self.assertEqual((inv.quantity,inv.reserved_quantity,inv.available_quantity),(100,99,1))
    def test_nonpositive_quantities_and_inactive_warehouse_cannot_be_used(self):
        for value in (0,-1,True,'1.5'):
            with self.assertRaises(ReservationError):self.place(items={self.skus[0].pk:value})
        wh=Warehouse.objects.create(name='停用仓',code='off',address='Test',is_active=False)
        Inventory.objects.create(sku=self.skus[0],warehouse=wh,quantity=100)
        self.assertEqual(available_quantity(self.skus[0]),0)
        self.assertEqual(InventoryService.get_available_quantity(self.skus[0].pk),0)
        with self.assertRaises(ReservationError):self.place()
    def test_ip_attempt_limit_survives_failed_checkout_and_new_accounts(self):
        with override_settings(RESERVATION_IP_REQUESTS_PER_MINUTE=1):
            with self.assertRaises(ReservationError):self.place(items={self.skus[0].pk:101})
            with self.assertRaises(ReservationError) as err:self.place(buyer=1)
            self.assertEqual(err.exception.code,'CHECKOUT_RATE_LIMITED')
    def test_cancelled_and_hidden_orders_keep_their_occupied_time_budget(self):
        order=self.place()[0]
        OrderInfo.objects.filter(pk=order.pk).update(created_time=timezone.now()-timedelta(minutes=5))
        close_order(order.pk,self.buyers[0].pk)
        OrderInfo.objects.filter(pk=order.pk).update(buyer_hidden=True)
        with override_settings(RESERVATION_MAX_HOLD_SECONDS_PER_HOUR=800):
            with self.assertRaises(ReservationError) as err:self.place()
        self.assertEqual(err.exception.code,'RESERVATION_TIME_BUDGET')
    def test_auth_ownership_request_id_and_legacy_return_do_not_mutate_payment(self):
        with patch('orders.views.get_redis_connection'):
            payload={'settlement_type':'1','address_id':self.addresses[0].pk,'sku_id':self.skus[0].pk,'buy_count':10,'request_id':uuid.uuid4().hex}
            path='/v1/orders/'+self.buyers[0].username
            self.assertEqual(self.client.post(path,json.dumps(payload),content_type='application/json').status_code,401)
            response=self.client.post(path,json.dumps(payload),content_type='application/json',**self.headers(self.buyers[0]))
            self.assertEqual(response.status_code,200);order=OrderInfo.objects.get()
            self.assertEqual(self.client.post(path,json.dumps(payload),content_type='application/json',**self.headers(self.buyers[0])).json()['data']['order_id'],order.pk)
            self.assertEqual(self.client.get('/v1/pays/notify',{'out_trade_no':order.pk}).status_code,302)
            order.refresh_from_db();self.assertEqual(order.status,1)
            self.assertEqual(self.client.get(path,{'type':'99'},**self.headers(self.buyers[0])).status_code,400)
            self.assertEqual(self.client.post('/v1/orders/'+self.buyers[1].username+'/cancel',{'order_id':order.pk},content_type='application/json',**self.headers(self.buyers[1])).status_code,404)
    @override_settings(ALIPAY_SELLER_ID='test-seller')
    def test_provider_notification_checks_signature_seller_app_amount_and_replay(self):
        from django.conf import settings
        order=self.place()[0]
        payload={'sign':'synthetic-signature','seller_id':'test-seller','app_id':settings.ALIPAY_APP_ID,'out_trade_no':order.pk,'trade_no':'provider-1','trade_status':'TRADE_SUCCESS','total_amount':str(order.total_amount)}
        with patch('pays.service.client') as client:
            client.return_value.verify.return_value=False
            self.assertEqual(self.client.post('/v1/pays/notify',payload).status_code,400)
            client.return_value.verify.return_value=True
            self.assertEqual(self.client.post('/v1/pays/notify',{**payload,'seller_id':'other'}).status_code,400)
            self.assertEqual(self.client.post('/v1/pays/notify',{**payload,'total_amount':'1'}).status_code,400)
            self.assertEqual(self.client.post('/v1/pays/notify',payload).content,b'success')
            self.assertEqual(self.client.post('/v1/pays/notify',payload).content,b'success')
        order.refresh_from_db();self.assertEqual(order.status,2)
    def test_policy_endpoint_cannot_edit_other_merchant_and_rejects_invalid_limits(self):
        url='/v1/supplier/reservation-policy';data={'ttl_seconds':600,'max_unpaid_quantity':200,'max_unpaid_amount':'20000','max_stock_percent':75,'change_reason':'按供货计划调整'}
        self.assertEqual(self.client.put(url,data,content_type='application/json',**self.headers(self.buyers[0])).status_code,403)
        self.assertEqual(self.client.put(url,data,content_type='application/json',**self.headers(self.shops[0])).status_code,200)
        self.assertEqual(ReservationPolicy.objects.get(merchant=self.shops[1]).max_stock_percent,100)
        self.assertEqual(self.client.put(url,{**data,'max_stock_percent':101},content_type='application/json',**self.headers(self.shops[0])).status_code,400)

    def test_cart_retry_after_clear_returns_original_order_and_ignores_forged_price(self):
        class Cart:
            def __init__(self,sku):self.rows={str(sku):json.dumps({'count':12,'status':True})}
            def hgetall(self,key):return dict(self.rows)
            def eval(self,script,keys,key,sku,original):
                if self.rows.get(sku)==original:self.rows.pop(sku)
        cart=Cart(self.skus[0].pk)
        payload={'settlement_type':'0','address_id':self.addresses[0].pk,'sku_list':[{'id':self.skus[0].pk,'price':0,'count':99999}],'request_id':uuid.uuid4().hex}
        with patch('orders.views.get_redis_connection',return_value=cart):
            url='/v1/orders/'+self.buyers[0].username
            first=self.client.post(url,payload,content_type='application/json',**self.headers(self.buyers[0]))
            self.assertEqual(first.status_code,200);self.assertEqual(cart.rows,{})
            retry=self.client.post(url,payload,content_type='application/json',**self.headers(self.buyers[0]))
        self.assertEqual(first.json(),retry.json());item=OrderGoods.objects.get()
        self.assertEqual((item.count,item.price),(12,Decimal('10')))

    def test_legacy_cart_input_guards_survive_reservation_checkout(self):
        class Cart:
            rows={}
            def hgetall(self,key):return self.rows
            def eval(self,*args):raise AssertionError('Invalid checkout must not clear cart')
        cart=Cart()
        payload={'settlement_type':'0','address_id':self.addresses[0].pk,'request_id':uuid.uuid4().hex}
        sku=self.skus[0].pk
        with patch('orders.views.get_redis_connection',return_value=cart):
            url='/v1/orders/'+self.buyers[0].username
            cart.rows={str(sku):json.dumps({'count':2,'status':True})}
            for selected in ('wrong',[None],[{'id':sku}]*2):
                with self.subTest(selected=selected):
                    response=self.client.post(url,{**payload,'sku_list':selected},content_type='application/json',**self.headers(self.buyers[0]))
                    self.assertEqual(response.status_code,400)
            for value in ('broken','[]','null',json.dumps({'count':2,'status':'true'})):
                with self.subTest(value=value):
                    cart.rows={str(sku):value}
                    self.assertEqual(self.client.post(url,payload,content_type='application/json',**self.headers(self.buyers[0])).status_code,400)
        self.assertFalse(OrderInfo.objects.exists())
        self.assertFalse(StockHold.objects.exists())

    def test_cart_and_merchant_adjustment_routes_enforce_ownership_and_reservation(self):
        with patch('carts.views.get_redis_connection'):
            self.assertEqual(self.client.post('/v1/carts/'+self.buyers[0].username,{'sku_id':self.skus[0].pk,'count':1},content_type='application/json',**self.headers(self.buyers[1])).status_code,403)
        self.place(items={self.skus[0].pk:99})
        from goods.merchant_views import _update_sku
        from django.test import RequestFactory
        request=RequestFactory().put('/isolated-update',{'stock':0},content_type='application/json');request.user_profile=self.shops[0]
        self.assertEqual(_update_sku(request,self.skus[0].pk).status_code,409)
        self.assertEqual(available_quantity(self.skus[0]),1)


@skipUnless(connection.vendor=='mysql','Requires real MySQL row locks and independent connections')
class ReservationConcurrencyTests(Fixtures,TransactionTestCase):
    def setUp(self):self.seed()
    def run_parallel(self,actions):
        barrier=Barrier(len(actions))
        def work(action):
            connections.close_all()
            try:
                barrier.wait(timeout=10)
                try:return action()
                except ReservationError as exc:return exc.code
            finally:connections.close_all()
        with ThreadPoolExecutor(max_workers=len(actions)) as pool:return list(pool.map(work,actions))
    def test_competing_99_and_50_never_both_reserve(self):
        result=self.run_parallel([lambda:self.place(buyer=0,items={self.skus[0].pk:99}),lambda:self.place(buyer=1,items={self.skus[0].pk:50})])
        self.assertEqual(sum(isinstance(r,list) for r in result),1,result)
        inv=Inventory.objects.get(sku=self.skus[0]);self.assertGreaterEqual(inv.available_quantity,0)
        self.assertEqual(inv.quantity,inv.reserved_quantity+inv.available_quantity)
    def test_cancel_racing_payment_cannot_release_paid_or_recreate_expired_stock(self):
        order=self.place()[0]
        self.run_parallel([lambda:close_order(order.pk,self.buyers[0].pk),lambda:confirm_payment(order.pk,'race-trade',order.total_amount)])
        order.refresh_from_db();inv=Inventory.objects.get(sku=self.skus[0])
        self.assertIn(order.status,(0,2));self.assertEqual(inv.reserved_quantity,10 if order.status==2 else 0)
        self.assertEqual(inv.quantity,100)
    def test_duplicate_shipping_consumes_once(self):
        order=self.place()[0];confirm_payment(order.pk,'ship-trade',order.total_amount)
        self.run_parallel([lambda:ship_order(order.pk,self.shops[0]),lambda:ship_order(order.pk,self.shops[0])])
        inv=Inventory.objects.get(sku=self.skus[0]);self.assertEqual((inv.quantity,inv.reserved_quantity),(90,0))
    def test_parallel_duplicate_checkout_key_creates_one_order(self):
        key=uuid.uuid4().hex
        rows=self.run_parallel([lambda:self.place(key=key),lambda:self.place(key=key)])
        self.assertEqual(rows[0][0].pk,rows[1][0].pk)
        self.assertEqual(OrderInfo.objects.count(),1);self.assertEqual(StockHold.objects.count(),1)
    @override_settings(RESERVATION_MAX_UNPAID_ORDERS=1)
    def test_parallel_different_skus_cannot_bypass_account_budget(self):
        rows=self.run_parallel([lambda:self.place(items={self.skus[0].pk:10}),lambda:self.place(items={self.skus[1].pk:10})])
        self.assertEqual(sum(isinstance(r,list) for r in rows),1)
        self.assertEqual(OrderInfo.objects.count(),1)
    def test_legacy_multi_sku_shipping_and_single_sku_shipping_share_lock_order(self):
        spu=self.skus[1].spu;spu.merchant=self.shops[0];spu.save()
        wh=Warehouse.objects.create(name='默认',code='DEFAULT',address='Synthetic')
        for sku in self.skus:Inventory.objects.create(sku=sku,warehouse=wh,quantity=100)
        def legacy(index,products):
            order=OrderInfo.objects.create(user_profile=self.buyers[index],order_id='legacy-%s'%index,total_amount=10*len(products),total_count=len(products),freight=0,status=2,receiver='Test',address='Synthetic',receiver_mobile='12345678901',tag='Test')
            for sku in products:OrderGoods.objects.create(order_info=order,sku=sku,count=1,price=10)
            return order
        first=legacy(0,self.skus);second=legacy(1,[self.skus[1]])
        result=self.run_parallel([lambda:ship_order(first.pk,self.shops[0]),lambda:ship_order(second.pk,self.shops[0])])
        self.assertTrue(all(isinstance(r,OrderInfo) for r in result),result)
        self.assertEqual(list(Inventory.objects.order_by('sku_id').values_list('quantity',flat=True)),[99,98])
