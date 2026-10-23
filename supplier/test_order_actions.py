"""Merchant mutation boundaries and subtype shipment; synthetic fixtures only."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import RequestFactory, TestCase, TransactionTestCase
from django.urls import resolve

from goods.models import Catalog, SKU, SPU
from inventory.models import Inventory, InventoryLog, Warehouse
from orders.models import OrderInfo, OrderGoods, TrialOrder, PreSaleOrder
from tea_saas.utils import jwt_encode
from users.models import UserProfile


class Fixtures:
    def setUp(self):
        self.shop = UserProfile.objects.create(username='shipshop', user_type='merchant', is_active=True)
        self.other = UserProfile.objects.create(username='othership', user_type='merchant', is_active=True)
        self.buyer = UserProfile.objects.create(username='shipbuyer', is_active=True)
        category = Catalog.objects.create(name='红茶')
        self.warehouse = Warehouse.objects.create(name='Synthetic', code='SHIP', address='Synthetic')
        self.skus = []
        for owner in (self.shop, self.other, self.shop):
            spu = SPU.objects.create(name='Synthetic tea', catalog=category, merchant=owner)
            sku = SKU.objects.create(spu=spu, name='100g', price=10, cost_price=5, market_price=12, stock=100)
            Inventory.objects.create(sku=sku, warehouse=self.warehouse, quantity=100)
            self.skus.append(sku)

    def order(self, key='single', *, kind='standard', status=2, subtype=None, paid=True, lines=None):
        lines = lines or [(self.skus[0], 2)]
        order = OrderInfo.objects.create(order_id=key, user_profile=self.buyer, order_type=kind,
            total_amount=sum(sku.price*count for sku,count in lines), total_count=sum(count for sku,count in lines),
            freight=0, status=status, receiver='Test', receiver_mobile='00000000000', address='Synthetic', tag='test')
        for sku,count in lines:
            OrderGoods.objects.create(order_info=order, sku=sku, count=count, price=sku.price)
        if kind == 'trial' and subtype is not None:
            TrialOrder.objects.create(order_info=order, status=subtype)
        if kind == 'presale' and subtype is not None:
            PreSaleOrder.objects.create(order_info=order, status=subtype, deposit_amount=4, balance_amount=16,
                                       deposit_paid=paid, balance_paid=paid)
        return order

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION':'Bearer '+jwt_encode({'id':(user or self.shop).pk})}

    def ship(self, order, user=None):
        return self.client.post('/v1/supplier/orders/'+order.pk+'/ship', **self.auth(user))

    def delete(self, order, user=None):
        return self.client.post('/v1/supplier/orders/delete', json.dumps({'order_id':order.pk}),
                                content_type='application/json', **self.auth(user))


class MerchantOrderActionsTests(Fixtures, TestCase):
    def test_standard_shipping_updates_only_this_merchant_and_only_once(self):
        order=self.order()
        self.assertEqual(self.ship(order).status_code,200)
        self.skus[0].refresh_from_db();self.skus[1].refresh_from_db();order.refresh_from_db()
        self.assertEqual((self.skus[0].stock,self.skus[1].stock,order.status),(98,100,3))
        self.assertEqual(Inventory.objects.get(sku=self.skus[0]).quantity,98)
        self.assertEqual(self.ship(order).status_code,200)
        self.assertEqual(InventoryLog.objects.filter(log_type='out').count(),1)

    def test_trial_ship_uses_subtype_status_and_preserves_base(self):
        order=self.order(kind='trial',status=None,subtype=2)
        self.assertEqual(self.ship(order).status_code,200)
        order.refresh_from_db()
        self.assertEqual(order.trialorder.status,3)
        self.assertIsNone(order.status)
        self.assertEqual(self.ship(order).status_code,200)

    def test_fully_paid_presale_ship_uses_subtype_status_and_preserves_base(self):
        order=self.order(kind='presale',status=None,subtype=4)
        self.assertEqual(self.ship(order).status_code,200)
        order.refresh_from_db()
        self.assertEqual(order.presaleorder.status,5)
        self.assertIsNone(order.status)
        self.assertEqual(self.ship(order).status_code,200)

    def test_unpaid_partial_cancelled_and_wrong_states_never_ship(self):
        orders=[self.order('unpaid',status=1),self.order('done',status=4),
            self.order('trial',kind='trial',status=2,subtype=7),
            self.order('deposit',kind='presale',status=2,subtype=4,paid=False),
            self.order('cancel',kind='presale',status=2,subtype=7)]
        for order in orders:
            with self.subTest(order=order.pk):self.assertEqual(self.ship(order).status_code,409)
        self.assertFalse(InventoryLog.objects.exists())

    def test_missing_subtype_cannot_advance(self):
        order=self.order(kind='trial',subtype=None)
        self.assertEqual(self.ship(order).status_code,409)

    def test_nonpositive_legacy_quantity_cannot_advance(self):
        order=self.order(lines=[(self.skus[0],0)])
        self.assertEqual(self.ship(order).status_code,409)
        order.refresh_from_db()
        self.assertEqual(order.status,2)
        self.assertFalse(InventoryLog.objects.exists())

    def test_foreign_merchant_cannot_ship_or_delete(self):
        order=self.order(status=1)
        self.assertEqual(self.ship(order,self.other).status_code,403)
        self.assertEqual(self.delete(order,self.other).status_code,403)
        self.assertTrue(OrderInfo.objects.filter(pk=order.pk).exists())

    def test_mixed_order_shipping_is_rejected_before_any_state_or_inventory_change(self):
        order=self.order(lines=[(self.skus[0],1),(self.skus[1],1)])
        for shop in (self.shop,self.other):self.assertEqual(self.ship(order,shop).status_code,409)
        order.refresh_from_db()
        self.assertEqual(order.status,2)
        self.assertEqual(list(SKU.objects.order_by('pk').values_list('stock',flat=True)),[100,100,100])
        self.assertFalse(InventoryLog.objects.exists())

    def test_mixed_order_deletion_preserves_both_merchants_lines(self):
        for status in (1,4):
            order=self.order('mixed'+str(status),status=status,lines=[(self.skus[0],1),(self.skus[1],1)])
            self.assertEqual(self.delete(order).status_code,409)
            self.assertEqual(order.ordergoods_set.count(),2)

    def test_missing_merchant_line_also_blocks_whole_order_action(self):
        SPU.objects.filter(pk=self.skus[1].spu_id).update(merchant=None)
        order=self.order(lines=[(self.skus[0],1),(self.skus[1],1)])
        self.assertEqual(self.ship(order).status_code,409)

    def test_insufficient_second_line_rolls_back_first_line_stock_logs_and_state(self):
        order=self.order(lines=[(self.skus[0],2),(self.skus[2],101)])
        self.assertEqual(self.ship(order).status_code,409)
        order.refresh_from_db();self.skus[0].refresh_from_db()
        self.assertEqual(order.status,2)
        self.assertEqual(self.skus[0].stock,100)
        self.assertEqual(Inventory.objects.get(sku=self.skus[0]).quantity,100)
        self.assertFalse(InventoryLog.objects.exists())

    def test_unpaid_cancellation_preserves_record_and_completed_is_not_deleted(self):
        unpaid=self.order('unpaid-cancel',status=1)
        self.assertEqual(self.delete(unpaid).status_code,200)
        unpaid.refresh_from_db();self.assertEqual(unpaid.status,0)
        complete=self.order('complete-preserved',status=4)
        self.assertEqual(self.delete(complete).status_code,409)
        self.assertTrue(OrderInfo.objects.filter(pk=complete.pk).exists())

    def test_subtype_active_state_cannot_use_legacy_base_to_delete(self):
        order=self.order(kind='trial',status=4,subtype=4)
        self.assertEqual(self.delete(order).status_code,409)

    def test_list_exposes_subtype_actions_and_hides_mixed_actions(self):
        trial=self.order('trial',kind='trial',status=None,subtype=2)
        presale=self.order('presale',kind='presale',status=None,subtype=4)
        mixed=self.order('mixed',lines=[(self.skus[0],1),(self.skus[1],1)])
        rows={row['order_id']:row for row in self.client.get('/v1/supplier/orders',**self.auth()).json()['data']}
        self.assertTrue(rows[trial.pk]['can_ship']);self.assertTrue(rows[presale.pk]['can_ship'])
        self.assertFalse(rows[mixed.pk]['can_ship']);self.assertFalse(rows[mixed.pk]['can_delete'])
        self.assertTrue(rows[mixed.pk]['requires_merchant_split'])
        self.assertEqual(rows[mixed.pk]['total_amount'],10)

    def test_pending_ship_filter_and_dashboard_include_real_subtypes(self):
        self.order('std');self.order('trial',kind='trial',status=None,subtype=2)
        self.order('presale',kind='presale',status=None,subtype=4)
        self.order('partial',kind='presale',status=None,subtype=4,paid=False)
        response=self.client.get('/v1/supplier/orders?status=unshipped',**self.auth())
        self.assertEqual({row['order_id'] for row in response.json()['data']},{'std','trial','presale'})
        summary=self.client.get('/v1/supplier/analytics',**self.auth()).json()['data']['summary']
        self.assertEqual(summary['pending_ship'],3)

    def test_inactive_and_nonmerchant_cannot_mutate(self):
        order=self.order()
        self.assertEqual(self.ship(order,self.buyer).status_code,403)
        self.shop.is_active=False;self.shop.save()
        self.assertEqual(self.ship(order).status_code,403)

    def test_subtypes_cannot_consume_reserved_stock_or_use_managed_flag(self):
        for kind, state in (('trial', 2), ('presale', 4)):
            with self.subTest(kind=kind):
                inv=Inventory.objects.get(sku=self.skus[0])
                inv.reserved_quantity=99;inv.save()
                order=self.order('reserved-'+kind,kind=kind,status=None,subtype=state)
                self.assertEqual(self.ship(order).status_code,409)
                inv.refresh_from_db()
                self.assertEqual((inv.quantity,inv.reserved_quantity,inv.available_quantity),(100,99,1))
                inv.reserved_quantity=0;inv.save()
                order.reservation_managed=True;order.save(update_fields=['reservation_managed'])
                self.assertEqual(self.ship(order).status_code,409)
        self.assertFalse(InventoryLog.objects.exists())

    def test_purchase_snapshot_still_owns_order_after_catalog_transfer(self):
        order=self.order()
        order.ordergoods_set.update(merchant_snapshot=self.shop)
        SPU.objects.filter(pk=self.skus[0].spu_id).update(merchant=self.other)
        self.assertEqual(self.ship(order,self.other).status_code,403)
        self.assertEqual(self.ship(order,self.shop).status_code,200)
        self.skus[0].refresh_from_db();self.assertEqual(self.skus[0].stock,98)

    def test_malformed_delete_has_no_effect(self):
        self.order()
        for data in ('broken','[]','{}'):
            response=self.client.post('/v1/supplier/orders/delete',data,content_type='application/json',**self.auth())
            self.assertEqual(response.status_code,400)
        self.assertEqual(OrderInfo.objects.count(),1)


@skipUnless(connection.vendor=='mysql','Requires isolated MySQL row locks')
class ConcurrentShipmentTests(Fixtures,TransactionTestCase):
    def test_concurrent_requests_deduct_only_once(self):
        order=self.order()
        barrier=Barrier(2)
        auth=self.auth()
        def ship_once():
            close_old_connections()
            try:
                request=RequestFactory().post('/v1/supplier/orders/'+order.pk+'/ship',**auth)
                route=resolve(request.path)
                barrier.wait(timeout=10)
                response=route.func(request,*route.args,**route.kwargs)
                return response.status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:ship_once(),range(2)))
        self.assertEqual(sorted(results),[200,200])
        self.skus[0].refresh_from_db()
        self.assertEqual(self.skus[0].stock,98)
        self.assertEqual(InventoryLog.objects.filter(log_type='out').count(),1)
