"""Buyer checkout payments; all provider calls use synthetic local doubles."""
from datetime import timedelta
from decimal import Decimal
from importlib import import_module
from importlib.util import find_spec
from unittest.mock import patch

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from inventory.models import Inventory
from orders.models import OrderInfo, ReservationRiskEvent, StockHold
from orders.reservations import ReservationError, close_order, confirm_payment, ship_order
from orders.test_reservations import Fixtures


class CombinedPaymentTests(Fixtures, TestCase):
    def setUp(self):
        self.seed()
        self.assertIsNotNone(find_spec('pays.combined'), 'Missing combined checkout payment capability')
        self.combined = import_module('pays.combined')
        models = import_module('pays.models')
        self.PaymentOrder = models.PaymentOrder
        self.PaymentAllocation = models.PaymentAllocation
        self.PaymentReceipt = models.PaymentReceipt
        self.orders = self.place(items={s.pk: index + 1 for index, s in enumerate(self.skus)})
        self.checkout_id = self.orders[0].checkout_request_id

    def prepare(self):
        return self.combined.prepare_checkout_payment(self.buyers[0], self.checkout_id)

    def pay(self, payment, trade='combined-trade', amount=None):
        return self.combined.confirm_combined_payment(
            payment.pk, trade, payment.total_amount if amount is None else amount)

    def test_prepare_preserves_shop_amounts_and_reuses_fixed_attempt_and_deadline(self):
        deadline = min(o.expires_at for o in self.orders)
        payment = self.prepare()
        self.assertTrue(payment.pk.startswith('pay_'))
        self.assertEqual((payment.total_amount, payment.currency, payment.expires_at),
                         (Decimal('30.00'), 'CNY', deadline))
        allocations = list(payment.allocations.order_by('order_id'))
        self.assertEqual(len(allocations), 2)
        self.assertEqual(sum(a.amount for a in allocations), payment.total_amount)
        for allocation in allocations:
            self.assertEqual(allocation.amount, allocation.goods_amount + allocation.freight_amount)
            self.assertEqual(allocation.merchant_id,
                             allocation.order.ordergoods_set.get().merchant_snapshot_id)
        with patch('pays.combined.timezone.now', return_value=timezone.now()+timedelta(seconds=30)):
            retry = self.prepare()
        self.assertEqual((retry.pk, retry.expires_at), (payment.pk, deadline))

    def test_only_remaining_unpaid_orders_are_charged_before_first_attempt(self):
        close_order(self.orders[0].pk, self.buyers[0].pk)
        payment = self.prepare()
        self.assertEqual(payment.total_amount, self.orders[1].total_amount)
        self.assertEqual(list(payment.allocations.values_list('order_id', flat=True)), [self.orders[1].pk])

    def test_three_merchants_use_one_payment_and_three_independent_orders(self):
        from goods.models import SPU, SKU
        from orders.models import ReservationPolicy
        from users.models import UserProfile
        merchant = UserProfile.objects.create(username='third-shop', user_type='merchant', is_active=True)
        spu = SPU.objects.create(name='Third tea', catalog=self.skus[0].spu.catalog, merchant=merchant)
        sku = SKU.objects.create(spu=spu, name='Third size', price=10, market_price=12,
                                 cost_price=5, stock=100, is_launched=True)
        ReservationPolicy.objects.create(merchant=merchant, max_stock_percent=100,
                                         max_unpaid_quantity=300)
        orders = self.place(buyer=1, items={self.skus[0].pk: 1, self.skus[1].pk: 2, sku.pk: 4})
        payment = self.combined.prepare_checkout_payment(self.buyers[1], orders[0].checkout_request_id)
        self.assertEqual((len(orders), payment.allocations.count(), payment.total_amount),
                         (3, 3, Decimal('70.00')))
        self.assertEqual(len(set(payment.allocations.values_list('merchant_id', flat=True))), 3)
        self.pay(payment)
        self.assertEqual(set(OrderInfo.objects.filter(pk__in=[o.pk for o in orders])
                             .values_list('status', flat=True)), {2})
        self.assertEqual(list(self.PaymentReceipt.objects.values_list('payment_id', 'amount')),
                         [(payment.pk, Decimal('70.00'))])

    def test_paid_order_is_excluded_before_first_attempt(self):
        confirm_payment(self.orders[0].pk, 'individual-first', self.orders[0].total_amount)
        payment = self.prepare()
        self.assertEqual(payment.total_amount, self.orders[1].total_amount)

    def test_prepare_rejects_other_buyer_inactive_account_and_merchant(self):
        for user in (self.buyers[1], self.shops[0]):
            with self.assertRaises(ReservationError):
                self.combined.prepare_checkout_payment(user, self.checkout_id)
        self.buyers[0].is_active = False
        self.buyers[0].save(update_fields=['is_active'])
        with self.assertRaises(ReservationError): self.prepare()
        self.assertFalse(self.PaymentOrder.objects.exists())

    def test_untrusted_currency_missing_hold_or_merchant_snapshot_are_rejected(self):
        target = self.orders[0]
        for changes in ({'currency': None}, {'reservation_managed': False}, {'order_type': 'trial'},
                        {'payment_trade_no': 'unconfirmed-historical-trade'}):
            original = {key: getattr(target, key) for key in changes}
            OrderInfo.objects.filter(pk=target.pk).update(**changes)
            with self.subTest(changes=changes), self.assertRaises(ReservationError): self.prepare()
            OrderInfo.objects.filter(pk=target.pk).update(**original)
        StockHold.objects.filter(item__order_info=target).update(state='released')
        with self.assertRaises(ReservationError): self.prepare()
        self.assertFalse(self.PaymentOrder.objects.exists())

    def test_changed_set_invalidates_persistently_and_never_reopens_at_new_amount(self):
        payment = self.prepare()
        close_order(self.orders[0].pk, self.buyers[0].pk)
        with self.assertRaises(ReservationError): self.prepare()
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'invalid')
        self.assertEqual(payment.total_amount, Decimal('30'))
        with self.assertRaises(ReservationError): self.prepare()
        self.assertEqual(self.PaymentOrder.objects.count(), 1)

    def test_changed_amount_invalidates_even_when_order_ids_match(self):
        payment = self.prepare()
        OrderInfo.objects.filter(pk=self.orders[0].pk).update(total_amount=99)
        with self.assertRaises(ReservationError): self.prepare()
        payment.refresh_from_db()
        self.assertEqual(payment.status, 'invalid')

    def test_allocation_snapshots_are_immutable(self):
        payment = self.prepare()
        allocation = payment.allocations.first()
        allocation.amount += Decimal('1')
        allocation.goods_amount += Decimal('1')
        with self.assertRaises(ValidationError): allocation.save()
        payment.total_amount += Decimal('1')
        with self.assertRaises(ValidationError): payment.save()

    def test_order_item_snapshot_currency_owner_and_amount_are_required(self):
        item = self.orders[0].ordergoods_set.get()
        for changes in ({'currency': None}, {'merchant_snapshot_id': None}, {'price': Decimal('0.01')}):
            original = {key: getattr(item, key) for key in changes}
            type(item).objects.filter(pk=item.pk).update(**changes)
            with self.subTest(changes=changes), self.assertRaises(ReservationError): self.prepare()
            type(item).objects.filter(pk=item.pk).update(**original)
        self.assertFalse(self.PaymentOrder.objects.exists())

    def test_receipt_must_target_exactly_one_payment_or_legacy_order(self):
        payment = self.prepare()
        defaults = {'trade_no': 'invalid-target', 'amount': payment.total_amount,
                    'currency': 'CNY', 'received_at': timezone.now(), 'outcome': 'pending'}
        for targets in ({}, {'payment': payment, 'legacy_order': self.orders[0]}):
            with self.assertRaises(IntegrityError), transaction.atomic():
                self.PaymentReceipt.objects.create(**defaults, **targets)

    def test_one_pending_attempt_and_allocation_amount_sum_are_database_constraints(self):
        payment = self.prepare()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.PaymentOrder.objects.create(buyer=self.buyers[0], checkout_id=self.checkout_id,
                currency='CNY', total_amount=30, expires_at=payment.expires_at)
        allocation = payment.allocations.first()
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.PaymentAllocation.objects.filter(pk=allocation.pk).update(amount=999)

    def test_nonzero_freight_is_allocated_once_in_addition_to_goods(self):
        order = self.orders[0]
        OrderInfo.objects.filter(pk=order.pk).update(freight=Decimal('4.25'),
            total_amount=order.total_amount + Decimal('4.25'))
        payment = self.prepare()
        allocation = payment.allocations.get(order=order)
        self.assertEqual((allocation.goods_amount, allocation.freight_amount, allocation.amount),
                         (Decimal('10'), Decimal('4.25'), Decimal('14.25')))
        self.assertEqual(payment.total_amount, Decimal('34.25'))
        self.pay(payment)

    def test_success_is_atomic_idempotent_and_does_not_copy_unique_trade_to_children(self):
        payment = self.pay(self.prepare())
        self.assertEqual(payment.status, 'paid')
        self.pay(payment)
        self.assertEqual(self.PaymentReceipt.objects.count(), 1)
        self.assertEqual(self.PaymentReceipt.objects.get().outcome, 'paid')
        self.assertEqual(set(payment.allocations.values_list('status', flat=True)), {'paid'})
        for order in self.orders:
            order.refresh_from_db()
            self.assertEqual(order.status, 2)
            self.assertIsNotNone(order.paid_at)
            self.assertIsNone(order.payment_trade_no)
            self.assertEqual(StockHold.objects.get(item__order_info=order).state, 'paid')

    def test_wrong_amount_or_incomplete_second_hold_rolls_back_everything(self):
        payment = self.prepare()
        with self.assertRaises(ReservationError): self.pay(payment, amount=Decimal('1'))
        StockHold.objects.filter(item__order_info=self.orders[1]).update(state='released')
        with self.assertRaises(ReservationError): self.pay(payment)
        self.assertEqual(OrderInfo.objects.filter(pk__in=[o.pk for o in self.orders], status=1).count(), 2)
        self.assertFalse(self.PaymentReceipt.objects.exists())
        self.assertEqual(StockHold.objects.get(item__order_info=self.orders[0]).state, 'reserved')

    def test_late_payment_keeps_full_receipt_releases_unpaid_holds_without_risk(self):
        payment = self.prepare()
        deadline = timezone.now()-timedelta(seconds=1)
        self.PaymentOrder.objects.filter(pk=payment.pk).update(expires_at=deadline)
        payment = self.pay(payment)
        self.assertEqual(payment.status, 'review')
        receipt = self.PaymentReceipt.objects.get()
        self.assertEqual((receipt.amount, receipt.outcome), (Decimal('30'), 'review'))
        self.assertEqual(set(OrderInfo.objects.filter(pk__in=[o.pk for o in self.orders]).values_list('close_reason', flat=True)), {'payment_review'})
        self.assertEqual(set(StockHold.objects.values_list('state', flat=True)), {'released'})
        self.assertFalse(ReservationRiskEvent.objects.exists())
        self.pay(payment)
        self.assertEqual(self.PaymentReceipt.objects.count(), 1)

    def test_cancel_then_late_receipt_never_revives_stock(self):
        payment = self.prepare()
        close_order(self.orders[0].pk, self.buyers[0].pk)
        self.pay(payment)
        self.assertEqual(OrderInfo.objects.filter(pk__in=[o.pk for o in self.orders], status=0).count(), 2)
        self.assertEqual(set(StockHold.objects.values_list('state', flat=True)), {'released'})
        self.assertEqual(self.PaymentReceipt.objects.get().outcome, 'review')
        self.assertEqual(ReservationRiskEvent.objects.count(), 1)

    def test_late_group_payment_preserves_legitimate_individual_payment(self):
        payment = self.prepare()
        paid = self.orders[0]
        confirm_payment(paid.pk, 'legacy-legitimate', paid.total_amount)
        ship_order(paid.pk, paid.ordergoods_set.get().merchant_snapshot)
        self.pay(payment)
        paid.refresh_from_db()
        self.assertEqual((paid.status, paid.payment_trade_no), (3, 'legacy-legitimate'))
        self.assertEqual(StockHold.objects.get(item__order_info=paid).state, 'consumed')
        self.orders[1].refresh_from_db()
        self.assertEqual(self.orders[1].status, 0)
        self.assertEqual(self.PaymentReceipt.objects.get(trade_no='combined-trade').outcome, 'review')

    def test_different_trade_duplicate_is_independent_review_receipt(self):
        payment = self.pay(self.prepare())
        original = list(OrderInfo.objects.order_by('pk').values('pk', 'status', 'paid_at',
                            'payment_trade_no', 'payment_exception'))
        self.pay(payment, trade='second-actual-receipt')
        self.pay(payment, trade='second-actual-receipt')
        self.assertEqual(self.PaymentReceipt.objects.count(), 2)
        self.assertEqual(self.PaymentReceipt.objects.get(trade_no='combined-trade').outcome, 'paid')
        self.assertEqual(self.PaymentReceipt.objects.get(trade_no='second-actual-receipt').outcome, 'review')
        self.assertEqual(set(StockHold.objects.values_list('state', flat=True)), {'paid'})
        self.assertEqual(OrderInfo.objects.filter(status=2).count(), 2)
        self.assertEqual(list(OrderInfo.objects.order_by('pk').values('pk', 'status', 'paid_at',
                            'payment_trade_no', 'payment_exception')), original)

    def test_legacy_paid_order_keeps_second_real_receipt_without_mutating_payment(self):
        order = self.orders[0]
        OrderInfo.objects.filter(pk=order.pk).update(checkout_request=None)
        confirm_payment(order.pk, 'legacy-first-receipt', order.total_amount)
        original = OrderInfo.objects.values().get(pk=order.pk)
        stock = list(Inventory.objects.order_by('pk').values())
        holds = list(StockHold.objects.order_by('pk').values())
        for _ in range(2):
            confirm_payment(order.pk, 'legacy-second-receipt', order.total_amount)
        extra = self.PaymentReceipt.objects.get(trade_no='legacy-second-receipt')
        self.assertEqual((extra.legacy_order_id, extra.amount, extra.outcome,
                          extra.review_reason), (order.pk, order.total_amount, 'review',
                          'duplicate_legacy_payment_review_required'))
        self.assertEqual(self.PaymentReceipt.objects.count(), 2)
        self.assertEqual(OrderInfo.objects.values().get(pk=order.pk), original)
        self.assertEqual(list(Inventory.objects.order_by('pk').values()), stock)
        self.assertEqual(list(StockHold.objects.order_by('pk').values()), holds)

    def test_same_trade_same_target_changed_amount_is_rejected_without_mutation(self):
        payment = self.pay(self.prepare())
        with self.assertRaises(ReservationError):
            self.pay(payment, amount=payment.total_amount + Decimal('1'))
        self.assertEqual(self.PaymentReceipt.objects.get().amount, Decimal('30'))
        self.assertEqual(OrderInfo.objects.filter(status=2).count(), 2)

    def test_receipt_trade_is_shared_with_legacy_orders(self):
        payment = self.pay(self.prepare())
        legacy = self.place(buyer=1, items={self.skus[0].pk: 3})[0]
        with self.assertRaises(ReservationError) as conflict:
            confirm_payment(legacy.pk, 'combined-trade', legacy.total_amount)
        self.assertEqual(conflict.exception.code, 'PAYMENT_TRADE_CONFLICT')
        legacy.refresh_from_db()
        self.assertEqual(legacy.status, 1)
        other = self.place(buyer=2, items={self.skus[1].pk: 3})[0]
        confirm_payment(other.pk, 'legacy-first', other.total_amount)
        with self.assertRaises(ReservationError) as conflict: self.pay(payment, trade='legacy-first')
        self.assertEqual(conflict.exception.code, 'PAYMENT_TRADE_CONFLICT')
        self.assertEqual(self.PaymentReceipt.objects.count(), 2)

    def test_independent_shipping_preserves_other_order_and_stock(self):
        self.pay(self.prepare())
        first, second = self.orders
        merchant = first.ordergoods_set.get().merchant_snapshot
        other_hold = StockHold.objects.get(item__order_info=second)
        before = Inventory.objects.get(pk=other_hold.inventory_id).quantity
        ship_order(first.pk, merchant)
        first.refresh_from_db(); second.refresh_from_db(); other_hold.refresh_from_db()
        self.assertEqual((first.status, second.status, other_hold.state), (3, 2, 'paid'))
        self.assertEqual(Inventory.objects.get(pk=other_hold.inventory_id).quantity, before)
        with self.assertRaises(ReservationError): ship_order(second.pk, merchant)
        ship_order(second.pk, second.ordergoods_set.get().merchant_snapshot)
        second.refresh_from_db()
        self.assertEqual(second.status, 3)


@override_settings(ALIPAY_SELLER_ID='synthetic-seller')
class CombinedPaymentHttpTests(Fixtures, TestCase):
    setUp = CombinedPaymentTests.setUp
    prepare = CombinedPaymentTests.prepare
    def test_endpoint_enforces_identity_json_and_ownership(self):
        url = '/v1/pays/checkout-payment'
        body = {'checkout_id': self.checkout_id, 'total_amount': '0.01'}
        self.assertEqual(self.client.post(url, body, content_type='application/json').status_code, 401)
        self.assertEqual(self.client.post(url, body, content_type='application/json', **self.headers(self.buyers[1])).status_code, 404)
        self.assertEqual(self.client.post(url, body, content_type='application/json', **self.headers(self.shops[0])).status_code, 403)
        self.assertEqual(self.client.post(url, '[]', content_type='application/json', **self.headers(self.buyers[0])).status_code, 400)
        self.assertEqual(self.client.get(url, **self.headers(self.buyers[0])).status_code, 405)
        with patch('pays.service.client') as provider:
            provider.return_value.api_alipay_trade_page_pay.return_value='synthetic-query'
            response = self.client.post(url, body, content_type='application/json', **self.headers(self.buyers[0]))
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()['data']
        self.assertEqual((data['checkout_id'], data['total_amount'], data['currency']), (self.checkout_id, '30.00', 'CNY'))
        self.assertEqual(len(data['orders']), 2)
        self.assertTrue(data['payment_id'].startswith('pay_'))
        self.assertEqual(provider.return_value.api_alipay_trade_page_pay.call_args.kwargs['out_trade_no'], data['payment_id'])

    def test_missing_configuration_returns_503_and_existing_order_entry_uses_group(self):
        from .service import payment_data
        with override_settings(ALIPAY_SELLER_ID=''):
            response = self.client.post('/v1/pays/checkout-payment', {'checkout_id': self.checkout_id},
                content_type='application/json', **self.headers(self.buyers[0]))
        self.assertEqual(response.status_code, 503)
        with patch('pays.service.client') as provider:
            provider.return_value.api_alipay_trade_page_pay.return_value='synthetic-query'
            data = payment_data(self.orders[0])
        self.assertEqual((data['checkout_id'], data['total_amount']), (self.checkout_id, '30.00'))

    def test_notification_routes_group_and_checks_signature_source_amount_and_get(self):
        payment = self.prepare()
        payload = {'sign':'synthetic', 'app_id': settings.ALIPAY_APP_ID,
            'seller_id':'synthetic-seller', 'out_trade_no': payment.pk,
            'trade_no':'notify-combined', 'trade_status':'TRADE_SUCCESS', 'total_amount':'30.00'}
        url = '/v1/pays/notify'
        self.assertEqual(self.client.get(url, payload).status_code, 302)
        with patch('pays.service.client') as provider:
            provider.return_value.verify.return_value=False
            self.assertEqual(self.client.post(url, payload).status_code, 400)
            provider.return_value.verify.return_value=True
            for bad in ({'seller_id':'other'}, {'app_id':'other'}, {'total_amount':'1.00'}):
                self.assertEqual(self.client.post(url, {**payload, **bad}).status_code, 400)
            self.assertFalse(self.PaymentReceipt.objects.exists())
            self.assertEqual(self.client.post(url, payload).content, b'success')
            self.assertEqual(self.client.post(url, payload).content, b'success')
        self.assertEqual(self.PaymentReceipt.objects.count(), 1)
        self.assertEqual(OrderInfo.objects.filter(status=2).count(), 2)
