"""Current R04/R07 contracts: visibility never performs financial/stock transitions."""
from decimal import Decimal
from unittest.mock import patch
from django.test import TestCase
from orders.test_reservations import Fixtures
from orders.models import OrderInfo,OrderGoods,TrialOrder,PreSaleOrder,StockHold,ReservationPolicyChange
from orders.reservations import (close_order,ship_order,merchant_actions,cancel_by_merchant,ReservationError)
from inventory.models import Inventory
from inventory.availability import available_quantity


class ReservationContractTests(Fixtures,TestCase):
    def setUp(self):self.seed()
    def legacy(self,kind='standard',state=2,products=None):
        products=products or [self.skus[0]]
        order=OrderInfo.objects.create(user_profile=self.buyers[1],order_id='legacy-'+str(OrderInfo.objects.count()),order_type=kind,
            status=state if kind=='standard' else None,total_amount=10*len(products),total_count=len(products),freight=0,
            receiver='Test',address='Synthetic',receiver_mobile='12345678901',tag='Test')
        for sku in products:OrderGoods.objects.create(order_info=order,sku=sku,count=1,price=10)
        return order
    def test_pending_hide_is_rejected_without_stock_or_state_changes(self):
        order=self.place()[0]
        with patch('orders.views.get_redis_connection'):
            url='/v1/orders/'+self.buyers[0].username+'/delete'
            response=self.client.post(url,{'order_id':order.pk},content_type='application/json',**self.headers(self.buyers[0]))
        self.assertEqual(response.status_code,409)
        order.refresh_from_db();self.assertEqual(order.status,1);self.assertFalse(order.buyer_hidden)
        self.assertEqual(StockHold.objects.get().state,'reserved');self.assertEqual(available_quantity(self.skus[0]),90)
    def test_cancel_then_hide_changes_only_visibility_and_preserves_release_history(self):
        order=self.place()[0];close_order(order.pk,self.buyers[0].pk)
        order.refresh_from_db()
        before=(order.closed_at,order.close_reason,list(StockHold.objects.values_list('state','quantity','released_at')))
        response=self.client.post('/v1/orders/'+self.buyers[0].username+'/delete',{'order_id':order.pk},content_type='application/json',**self.headers(self.buyers[0]))
        self.assertEqual(response.status_code,200);order.refresh_from_db();self.assertTrue(order.buyer_hidden)
        self.assertEqual((order.closed_at,order.close_reason,list(StockHold.objects.values_list('state','quantity','released_at'))),before)
        self.assertEqual(available_quantity(self.skus[0]),100)
    def test_trial_and_presale_use_child_status_and_ship_only_once(self):
        trial=self.legacy('trial');TrialOrder.objects.create(order_info=trial,status=2)
        self.assertTrue(merchant_actions(trial,self.shops[0])['can_ship'])
        ship_order(trial.pk,self.shops[0]);ship_order(trial.pk,self.shops[0]);trial.refresh_from_db()
        self.assertIsNone(trial.status);self.assertEqual(TrialOrder.objects.get().status,3)
        presale=self.legacy('presale');child=PreSaleOrder.objects.create(order_info=presale,status=4,deposit_amount=2,balance_amount=8,deposit_paid=True,balance_paid=False)
        self.assertFalse(merchant_actions(presale,self.shops[0])['can_ship'])
        with self.assertRaises(ReservationError):ship_order(presale.pk,self.shops[0])
        child.balance_paid=True;child.save();ship_order(presale.pk,self.shops[0]);ship_order(presale.pk,self.shops[0]);child.refresh_from_db();presale.refresh_from_db()
        self.assertEqual(child.status,5);self.assertIsNone(presale.status)
        self.assertEqual(Inventory.objects.get(sku=self.skus[0]).quantity,98)
    def test_subtype_missing_or_managed_or_foreign_and_mixed_orders_are_rejected(self):
        missing=self.legacy('trial')
        with self.assertRaises(ReservationError):ship_order(missing.pk,self.shops[0])
        missing.reservation_managed=True;missing.save();TrialOrder.objects.create(order_info=missing,status=2)
        with self.assertRaises(ReservationError):ship_order(missing.pk,self.shops[0])
        mixed=self.legacy(products=self.skus)
        for shop in self.shops:
            self.assertEqual(merchant_actions(mixed,shop),{'can_ship':False,'can_cancel':False})
            with self.assertRaises(ReservationError):ship_order(mixed.pk,shop)
            with self.assertRaises(ReservationError):cancel_by_merchant(mixed.pk,shop)
    def test_legacy_subtype_cannot_consume_another_orders_reserved_quantity(self):
        self.place(items={self.skus[0].pk:99})
        trial=self.legacy('trial');TrialOrder.objects.create(order_info=trial,status=2)
        OrderGoods.objects.filter(order_info=trial).update(count=50);trial.total_count=50;trial.save()
        with self.assertRaises(ValueError):ship_order(trial.pk,self.shops[0])
        self.assertEqual(TrialOrder.objects.get().status,2)
        inv=Inventory.objects.get(sku=self.skus[0]);self.assertEqual((inv.quantity,inv.reserved_quantity,inv.available_quantity),(100,99,1))
    def test_merchant_cancel_retains_record_and_completed_cannot_cancel(self):
        order=self.place()[0]
        cancel_by_merchant(order.pk,self.shops[0]);cancel_by_merchant(order.pk,self.shops[0])
        order.refresh_from_db();self.assertEqual((order.status,order.close_reason),(0,'merchant_cancel'))
        completed=self.legacy(state=4)
        with self.assertRaises(ReservationError):cancel_by_merchant(completed.pk,self.shops[0])
        self.assertTrue(OrderInfo.objects.filter(pk=completed.pk).exists())
    def test_policy_change_requires_basis_and_records_actor_before_after_atomically(self):
        original=self.place()[0];deadline=original.expires_at
        data={'ttl_seconds':300,'max_unpaid_quantity':90,'max_unpaid_amount':'9000','max_stock_percent':40,'change_reason':'按包装与本周供货计划调整'}
        url='/v1/supplier/reservation-policy';headers=self.headers(self.shops[0])
        self.assertEqual(self.client.put(url,{k:v for k,v in data.items() if k!='change_reason'},content_type='application/json',**headers).status_code,400)
        self.assertFalse(ReservationPolicyChange.objects.exists())
        self.assertEqual(self.client.put(url,data,content_type='application/json',**headers).status_code,200)
        audit=ReservationPolicyChange.objects.get()
        self.assertEqual(audit.actor_id,self.shops[0].pk);self.assertEqual(audit.merchant_id,self.shops[0].pk)
        self.assertEqual(audit.before['ttl_seconds'],600);self.assertEqual(audit.after['ttl_seconds'],300);self.assertEqual(audit.reason,data['change_reason'])
        self.assertTrue(audit.effective_at)
        original.refresh_from_db();self.assertEqual(original.expires_at,deadline)
        new=self.place(buyer=1)[0]
        self.assertEqual(round((new.expires_at-new.created_time).total_seconds()),300)
