"""Real PostgreSQL proofs for short checkout transactions and fixed holds.

Run only against the isolated PostgreSQL test database. Events coordinate the
transactions; pg_blocking_pids proves a lock wait instead of guessing by sleep.
Shared warehouses may serialize otherwise independent SKU reservations.
"""
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier, Event
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection, connections, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from goods.models import SKU
from inventory.models import Inventory, InventoryLog, Warehouse
from .models import CartCleanupTask, CheckoutRequest, OrderGoods, OrderInfo, StockHold
from .reservations import (
    ReservationError, close_order, confirm_payment, create_orders, expire_orders,
)
from .test_reservations import Fixtures


@skipUnless(connection.vendor == 'postgresql',
            'Requires PostgreSQL row locks and independent connections')
class CheckoutLightConcurrencyTests(Fixtures, TransactionTestCase):
    def setUp(self):
        self.seed()
        self.warehouse = Warehouse.objects.create(
            name='Synthetic checkout warehouse', code='LIGHT', address='Synthetic')
        for sku in self.skus:
            Inventory.objects.create(sku=sku, warehouse=self.warehouse, quantity=100)

    def _place(self, buyer=0, items=None, key=None, digest='same', snapshots=None):
        return create_orders(
            self.buyers[buyer], key or uuid.uuid4().hex, digest,
            self.addresses[buyer].pk, items or {self.skus[0].pk: 10},
            '198.51.100.%s' % (buyer + 1), cart_snapshots=snapshots,
        )

    def _worker(self, action):
        # Django connections are thread-local; each action opens and closes its
        # own real database connection, including when an assertion fails.
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

    def _parallel(self, actions):
        barrier = Barrier(len(actions))

        def coordinated(action):
            def run(pid):
                barrier.wait(timeout=10)
                try:
                    return action()
                except ReservationError as exc:
                    return exc.code
            return self._worker(run)

        with ThreadPoolExecutor(max_workers=len(actions)) as pool:
            futures = [pool.submit(coordinated, action) for action in actions]
            return [future.result(timeout=20) for future in futures]

    def _assert_blocked_by(self, waiter, holder):
        deadline = time.monotonic() + 5
        poll = Event()
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                cursor.execute('SELECT %s = ANY(pg_blocking_pids(%s))',
                               [holder, waiter])
                if cursor.fetchone()[0]:
                    return
            # Poll an actual PostgreSQL lock condition, never infer blocking
            # from a fixed elapsed delay or from Future.done() alone.
            poll.wait(0.01)
        self.fail('Backend %s did not block on backend %s' % (waiter, holder))

    @staticmethod
    def _snapshots(items):
        return {sid: {'generation': 'synthetic-%s' % sid, 'version': 1,
                      'removed': 0, 'added': count}
                for sid, count in items.items()}

    def test_abc_wins_b_and_failed_bd_leaves_no_d_side_effects(self):
        a = self.skus[0]
        extra = [SKU.objects.create(
            spu=a.spu, name=name, price=10, market_price=12, cost_price=5,
            stock=100, is_launched=True) for name in ('B', 'C', 'D')]
        for sku in extra:
            Inventory.objects.create(sku=sku, warehouse=self.warehouse, quantity=100)
        b, c, d = extra
        abc = {a.pk: 70, b.pk: 70, c.pk: 70}
        bd = {b.pk: 50, d.pk: 50}
        winner_key, loser_key = uuid.uuid4().hex, uuid.uuid4().hex
        locked, release, loser_started = Event(), Event(), Event()
        pids = {}

        def winner(pid):
            pids['winner'] = pid
            with transaction.atomic():
                orders = self._place(items=abc, key=winner_key,
                                     snapshots=self._snapshots(abc))
                locked.set()
                self.assertTrue(release.wait(12), 'Winner was not released')
            return orders

        def loser(pid):
            pids['loser'] = pid
            loser_started.set()
            try:
                self._place(buyer=1, items=bd, key=loser_key,
                            snapshots=self._snapshots(bd))
            except ReservationError as exc:
                return exc.code
            return 'unexpected_success'

        with ThreadPoolExecutor(max_workers=2) as pool:
            won = pool.submit(self._worker, winner)
            try:
                self.assertTrue(locked.wait(10), 'ABC failed before holding stock')
                lost = pool.submit(self._worker, loser)
                self.assertTrue(loser_started.wait(5))
                self.assertNotEqual(pids['winner'], pids['loser'])
                self._assert_blocked_by(pids['loser'], pids['winner'])
            finally:
                release.set()
            self.assertEqual(len(won.result(timeout=20)), 1)
            self.assertEqual(lost.result(timeout=20), 'INSUFFICIENT_STOCK')

        self.assertEqual(OrderInfo.objects.count(), 1)
        self.assertEqual(CheckoutRequest.objects.count(), 1)
        self.assertFalse(CheckoutRequest.objects.filter(request_id=loser_key).exists())
        self.assertEqual(OrderGoods.objects.count(), 3)
        self.assertEqual(StockHold.objects.count(), 3)
        self.assertEqual(CartCleanupTask.objects.count(), 3)
        for sku in (a, b, c):
            ledger = Inventory.objects.get(sku=sku)
            self.assertEqual((ledger.quantity, ledger.reserved_quantity,
                              ledger.available_quantity), (100, 70, 30))
        ledger = Inventory.objects.get(sku=d)
        self.assertEqual((ledger.quantity, ledger.reserved_quantity,
                          ledger.available_quantity), (100, 0, 100))
        self.assertFalse(OrderGoods.objects.filter(sku=d).exists())
        self.assertFalse(StockHold.objects.filter(inventory=ledger).exists())
        self.assertFalse(CartCleanupTask.objects.filter(sku_id=d.pk).exists())
        self.assertFalse(InventoryLog.objects.filter(sku=d).exists())

    def test_abundant_same_sku_reservations_add_up_across_buyers(self):
        quantities = (11, 17, 23)
        actions = [lambda i=i, count=count: self._place(
            buyer=i, items={self.skus[0].pk: count})
            for i, count in enumerate(quantities)]
        results = self._parallel(actions)
        self.assertTrue(all(isinstance(result, list) for result in results), results)
        self.assertEqual(OrderInfo.objects.count(), 3)
        self.assertEqual(StockHold.objects.count(), 3)
        self.assertEqual(sum(StockHold.objects.values_list('quantity', flat=True)), 51)
        ledger = Inventory.objects.get(sku=self.skus[0])
        self.assertEqual((ledger.quantity, ledger.reserved_quantity,
                          ledger.available_quantity), (100, 51, 49))

    def test_parallel_replay_and_conflicting_intent_never_renew_the_hold(self):
        key = uuid.uuid4().hex
        started = timezone.now().replace(microsecond=0)
        with patch('orders.reservations.timezone.now', return_value=started):
            order = self._place(key=key, digest='original')[0]
        expected_expiry = started + timedelta(seconds=900)
        self.assertEqual(order.expires_at, expected_expiry)
        with patch('orders.reservations.timezone.now',
                   return_value=started + timedelta(seconds=300)):
            results = self._parallel([
                lambda: self._place(key=key, digest='original'),
                lambda: self._place(key=key, digest='changed'),
            ])
        self.assertEqual(results[0][0].pk, order.pk)
        self.assertEqual(results[1], 'IDEMPOTENCY_CONFLICT')
        order.refresh_from_db()
        self.assertEqual(order.expires_at, expected_expiry)
        self.assertEqual(OrderInfo.objects.count(), 1)
        self.assertEqual(CheckoutRequest.objects.count(), 1)
        self.assertEqual(StockHold.objects.count(), 1)
        self.assertEqual(Inventory.objects.get(sku=self.skus[0]).reserved_quantity, 10)

    def test_pending_order_does_not_keep_inventory_locked_after_commit(self):
        committed, release = Event(), Event()
        checkout_state = {}

        def checkout(pid):
            order = self._place()[0]
            checkout_state.update(pid=pid, order_id=order.pk)
            committed.set()
            # Keep the original session alive: closing it would also release
            # locks and could hide a transaction accidentally kept open.
            self.assertTrue(release.wait(12), 'Checkout session was not released')
            return pid, order.pk

        def acquire(pid):
            with transaction.atomic():
                ledger = Inventory.objects.select_for_update(nowait=True).get(
                    sku=self.skus[0])
                return pid, ledger.reserved_quantity

        with ThreadPoolExecutor(max_workers=2) as pool:
            placed = pool.submit(self._worker, checkout)
            try:
                self.assertTrue(committed.wait(10))
                order = OrderInfo.objects.get(pk=checkout_state['order_id'])
                self.assertEqual(order.status, 1)
                next_pid, reserved = pool.submit(self._worker, acquire).result(timeout=10)
                self.assertNotEqual(checkout_state['pid'], next_pid)
            finally:
                release.set()
            _, order_id = placed.result(timeout=20)
        self.assertEqual(reserved, 10)
        order = OrderInfo.objects.get(pk=order_id)
        self.assertEqual(order.status, 1)
        self.assertIsNone(order.paid_at)
        self.assertEqual(StockHold.objects.get().state, 'reserved')

    def test_900_second_boundary_releases_once_and_paid_hold_survives(self):
        started = timezone.now().replace(microsecond=0)
        with patch('orders.reservations.timezone.now', return_value=started):
            unpaid = self._place()[0]
            paid = self._place(buyer=1)[0]
            confirm_payment(paid.pk, 'synthetic-paid', paid.total_amount)
        self.assertEqual(unpaid.expires_at, started + timedelta(seconds=900))
        self.assertEqual(paid.expires_at, started + timedelta(seconds=900))
        with patch('orders.reservations.timezone.now',
                   return_value=started + timedelta(seconds=899)):
            self.assertEqual(expire_orders(), 0)
        self.assertEqual(Inventory.objects.get(sku=self.skus[0]).reserved_quantity, 20)
        with patch('orders.reservations.timezone.now',
                   return_value=started + timedelta(seconds=900)):
            self.assertEqual(expire_orders(), 1)
            self.assertEqual(expire_orders(), 0)
        unpaid.refresh_from_db()
        paid.refresh_from_db()
        self.assertEqual((unpaid.status, unpaid.close_reason), (0, 'expired'))
        self.assertEqual(paid.status, 2)
        self.assertEqual(StockHold.objects.get(item__order_info=unpaid).state, 'released')
        self.assertEqual(StockHold.objects.get(item__order_info=paid).state, 'paid')
        ledger = Inventory.objects.get(sku=self.skus[0])
        self.assertEqual((ledger.quantity, ledger.reserved_quantity,
                          ledger.available_quantity), (100, 10, 90))
        self.assertEqual(InventoryLog.objects.filter(log_type='release').count(), 1)

    def test_payment_racing_expiry_at_deadline_cannot_revive_stock(self):
        started = timezone.now().replace(microsecond=0)
        with patch('orders.reservations.timezone.now', return_value=started):
            order = self._place()[0]
        with patch('orders.reservations.timezone.now',
                   return_value=started + timedelta(seconds=900)):
            results = self._parallel([
                lambda: close_order(order.pk, reason='expired', expired_only=True),
                lambda: confirm_payment(order.pk, 'synthetic-late', order.total_amount),
            ])
        self.assertTrue(all(isinstance(result, OrderInfo) for result in results), results)
        order.refresh_from_db()
        self.assertEqual(order.status, 0)
        self.assertEqual(order.payment_exception, 'late_payment_refund_required')
        self.assertEqual(StockHold.objects.get().state, 'released')
        self.assertEqual(InventoryLog.objects.filter(log_type='release').count(), 1)
        ledger = Inventory.objects.get(sku=self.skus[0])
        self.assertEqual((ledger.quantity, ledger.reserved_quantity,
                          ledger.available_quantity), (100, 0, 100))

    def test_warehouse_disable_waits_for_checkout_commit(self):
        locked, release, disabling = Event(), Event(), Event()
        pids = {}

        def checkout(pid):
            pids['checkout'] = pid
            with transaction.atomic():
                order = self._place()[0]
                locked.set()
                self.assertTrue(release.wait(12), 'Checkout was not released')
            return order.pk

        def disable(pid):
            pids['disable'] = pid
            disabling.set()
            return Warehouse.objects.filter(pk=self.warehouse.pk).update(is_active=False)

        with ThreadPoolExecutor(max_workers=2) as pool:
            placed = pool.submit(self._worker, checkout)
            try:
                self.assertTrue(locked.wait(10))
                disabled = pool.submit(self._worker, disable)
                self.assertTrue(disabling.wait(5))
                self.assertNotEqual(pids['checkout'], pids['disable'])
                self._assert_blocked_by(pids['disable'], pids['checkout'])
                self.warehouse.refresh_from_db()
                self.assertTrue(self.warehouse.is_active)
            finally:
                release.set()
            order_id = placed.result(timeout=20)
            self.assertEqual(disabled.result(timeout=20), 1)
        self.warehouse.refresh_from_db()
        self.assertFalse(self.warehouse.is_active)
        self.assertEqual(OrderInfo.objects.get(pk=order_id).status, 1)
        self.assertEqual(Inventory.objects.get(sku=self.skus[0]).reserved_quantity, 10)
