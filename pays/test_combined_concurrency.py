"""Combined-payment lifecycle proofs using independent PostgreSQL sessions.

Each ordered race keeps the winning action's outer transaction open, proves
the competing session is blocked by it, then commits. No provider is called.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from threading import Event
from unittest import skipUnless

from django.db import connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from inventory.models import Inventory, InventoryLog
from orders.models import OrderInfo, ReservationRiskEvent, StockHold
from orders.reservations import (
    ReservationError, close_order, confirm_payment, expire_orders,
)
from orders.test_reservations import Fixtures
from pays.combined import confirm_combined_payment, prepare_checkout_payment
from pays.models import PaymentOrder, PaymentReceipt


@skipUnless(connection.vendor == 'postgresql',
            'Requires PostgreSQL row locks and independent sessions')
class CombinedPaymentConcurrencyTests(Fixtures, TransactionTestCase):
    def setUp(self):
        self.seed()
        # Hand-checked payable amounts: shop 0 = 10; shop 1 = 20.
        self.orders = self.place(items={self.skus[0].pk: 1, self.skus[1].pk: 2})
        self.payment = prepare_checkout_payment(
            self.buyers[0], self.orders[0].checkout_request_id)
        self.assertEqual(self.payment.total_amount, Decimal('30.00'))

    def _worker(self, action):
        # Connections are thread-local. Always close every worker connection,
        # including assertion/SQL failures, so test-database disposal is safe.
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '8s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute('SELECT pg_backend_pid()')
                pid = cursor.fetchone()[0]
            return action(pid)
        finally:
            connections.close_all()

    def _assert_blocked_by(self, waiter, holder):
        deadline = time.monotonic() + 5
        poll = Event()
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute('SELECT %s = ANY(pg_blocking_pids(%s))',
                               [holder, waiter])
                if cursor.fetchone()[0]:
                    return
            poll.wait(0.01)
        self.fail('Backend %s did not block on backend %s' % (waiter, holder))

    @staticmethod
    def _run_action(action):
        try:
            return action()
        except ReservationError as exc:
            return exc.code

    def _wait_for_worker(self, ready, future, timeout, message):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if future.done():
                # Surface the worker's original traceback, including failures
                # before its ready event, instead of hiding it as a timeout.
                future.result()
            if ready.wait(0.01):
                return
        if future.done():
            future.result()
        self.fail(message)

    def _ordered_race(self, winning_action, competing_action):
        locked, release, started = Event(), Event(), Event()
        pids = {}

        def winner(pid):
            pids['winner'] = pid
            with transaction.atomic():
                result = winning_action()
                locked.set()
                self.assertTrue(release.wait(12), 'Winning transaction was not released')
            return result

        def competitor(pid):
            pids['competitor'] = pid
            started.set()
            return self._run_action(competing_action)

        with ThreadPoolExecutor(max_workers=2) as pool:
            won = pool.submit(self._worker, winner)
            try:
                self._wait_for_worker(locked, won, 10,
                                      'Winning action did not reach its lock hold')
                competed = pool.submit(self._worker, competitor)
                self._wait_for_worker(started, competed, 5,
                                      'Competing session did not start')
                self.assertNotEqual(pids['winner'], pids['competitor'])
                self._assert_blocked_by(pids['competitor'], pids['winner'])
            finally:
                release.set()
            return won.result(timeout=20), competed.result(timeout=20)

    def _pay(self, trade='race-combined'):
        return confirm_combined_payment(self.payment.pk, trade, Decimal('30.00')).status

    def _cancel(self):
        return close_order(self.orders[0].pk, self.buyers[0].pk).status

    def _assert_paid_group(self):
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'paid')
        self.assertEqual(set(self.payment.allocations.values_list('status', flat=True)), {'paid'})
        for order in self.orders:
            order.refresh_from_db()
            self.assertEqual(order.status, 2)
            self.assertIsNotNone(order.paid_at)
            self.assertIsNone(order.payment_trade_no)
        self.assertEqual(set(StockHold.objects.filter(
            item__order_info__in=self.orders).values_list('state', flat=True)), {'paid'})
        self.assertEqual(
            list(Inventory.objects.filter(sku__in=self.skus).order_by('sku_id')
                 .values_list('quantity', 'reserved_quantity', 'available_quantity')),
            [(100, 1, 99), (100, 2, 98)])
        self.assertFalse(InventoryLog.objects.filter(log_type='release').exists())
        self.assertFalse(ReservationRiskEvent.objects.exists())

    def _assert_review_without_stock(self, risk_kind):
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'review')
        self.assertEqual(set(self.payment.allocations.values_list('status', flat=True)), {'review'})
        for order in self.orders:
            order.refresh_from_db()
            self.assertEqual(order.status, 0)
            self.assertIsNone(order.paid_at)
        receipt = PaymentReceipt.objects.get()
        self.assertEqual((receipt.payment_id, receipt.amount, receipt.currency, receipt.outcome),
                         (self.payment.pk, Decimal('30.00'), 'CNY', 'review'))
        self.assertEqual(set(StockHold.objects.values_list('state', flat=True)), {'released'})
        self.assertEqual(
            list(Inventory.objects.filter(sku__in=self.skus).order_by('sku_id')
                 .values_list('quantity', 'reserved_quantity', 'available_quantity')),
            [(100, 0, 100), (100, 0, 100)])
        self.assertEqual(InventoryLog.objects.filter(log_type='release').count(), 2)
        self.assertEqual(ReservationRiskEvent.objects.count(), 1)
        self.assertEqual(ReservationRiskEvent.objects.get().kind, risk_kind)

    def test_identical_callbacks_wait_then_confirm_every_child_exactly_once(self):
        self.assertEqual(self._ordered_race(self._pay, self._pay), ('paid', 'paid'))
        self._assert_paid_group()
        receipt = PaymentReceipt.objects.get()
        self.assertEqual((receipt.trade_no, receipt.payment_id, receipt.outcome),
                         ('race-combined', self.payment.pk, 'paid'))

    def test_combined_trade_wins_against_another_buyers_legacy_callback(self):
        legacy = self.place(buyer=1, items={self.skus[0].pk: 3})[0]
        self.assertEqual(legacy.total_amount, Decimal('30.00'))
        result = self._ordered_race(
            lambda: self._pay('shared-trade'),
            lambda: confirm_payment(legacy.pk, 'shared-trade', Decimal('30.00')).status)
        self.assertEqual(result, ('paid', 'PAYMENT_TRADE_CONFLICT'))
        receipt = PaymentReceipt.objects.get()
        self.assertEqual((receipt.payment_id, receipt.legacy_order_id, receipt.outcome),
                         (self.payment.pk, None, 'paid'))
        legacy.refresh_from_db()
        self.assertEqual((legacy.status, legacy.paid_at, legacy.payment_trade_no), (1, None, None))
        self.assertEqual(StockHold.objects.get(item__order_info=legacy).state, 'reserved')
        self.assertEqual(set(OrderInfo.objects.filter(pk__in=[o.pk for o in self.orders])
                             .values_list('status', flat=True)), {2})

    def test_legacy_trade_wins_against_another_buyers_combined_callback(self):
        legacy = self.place(buyer=1, items={self.skus[0].pk: 3})[0]
        result = self._ordered_race(
            lambda: confirm_payment(legacy.pk, 'shared-trade', Decimal('30.00')).status,
            lambda: self._pay('shared-trade'))
        self.assertEqual(result, (2, 'PAYMENT_TRADE_CONFLICT'))
        receipt = PaymentReceipt.objects.get()
        self.assertEqual((receipt.payment_id, receipt.legacy_order_id, receipt.outcome),
                         (None, legacy.pk, 'paid'))
        legacy.refresh_from_db()
        self.assertEqual((legacy.status, legacy.payment_trade_no), (2, 'shared-trade'))
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, 'pending')
        self.assertEqual(set(OrderInfo.objects.filter(pk__in=[o.pk for o in self.orders])
                             .values_list('status', flat=True)), {1})
        self.assertEqual(set(StockHold.objects.filter(item__order_info__in=self.orders)
                             .values_list('state', flat=True)), {'reserved'})

    def test_payment_commits_before_cancellation_without_releasing_paid_stock(self):
        self.assertEqual(self._ordered_race(self._pay, self._cancel),
                         ('paid', 'ORDER_NOT_CANCELLABLE'))
        self._assert_paid_group()
        self.assertEqual(PaymentReceipt.objects.count(), 1)

    def test_cancellation_commits_before_payment_and_full_receipt_requires_review(self):
        self.assertEqual(self._ordered_race(self._cancel, self._pay), (0, 'review'))
        self._assert_review_without_stock('cancel')
        self.assertEqual(self._pay(), 'review')
        self._assert_review_without_stock('cancel')

    def test_expiry_commits_before_late_callback_without_revival_or_double_release(self):
        # Only shop 0 is due; its expiry invalidates the issued total. The
        # callback must release shop 1 without attributing another buyer abuse.
        OrderInfo.objects.filter(pk=self.orders[0].pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self._ordered_race(
            lambda: expire_orders(user_id=self.buyers[0].pk), self._pay), (1, 'review'))
        self._assert_review_without_stock('timeout')
        self.assertEqual(expire_orders(user_id=self.buyers[0].pk), 0)
        self.assertEqual(self._pay(), 'review')
        self._assert_review_without_stock('timeout')

    def test_old_child_link_after_combined_payment_preserves_lawful_payment(self):
        self.assertEqual(self._pay(), 'paid')
        original = list(OrderInfo.objects.filter(pk__in=[o.pk for o in self.orders])
                        .order_by('pk').values('pk', 'status', 'paid_at',
                                              'payment_trade_no', 'payment_exception'))
        child = self.orders[0]
        confirm_payment(child.pk, 'late-child-link', Decimal('10.00'))
        confirm_payment(child.pk, 'late-child-link', Decimal('10.00'))
        self._assert_paid_group()
        self.assertEqual(PaymentReceipt.objects.count(), 2)
        receipt = PaymentReceipt.objects.get(trade_no='late-child-link')
        self.assertEqual((receipt.payment_id, receipt.legacy_order_id, receipt.amount,
                          receipt.outcome, receipt.review_reason),
                         (None, child.pk, Decimal('10.00'), 'review',
                          'duplicate_legacy_payment_review_required'))
        self.assertEqual(list(OrderInfo.objects.filter(pk__in=[o.pk for o in self.orders])
                              .order_by('pk').values('pk', 'status', 'paid_at',
                                                    'payment_trade_no', 'payment_exception')),
                         original)
