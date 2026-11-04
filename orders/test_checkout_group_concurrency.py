"""Real PostgreSQL serialization of checkout-group admission and lifecycle.

Workers own independent database sessions. Barrier tests exercise the last slot;
Event tests hold actual transactions until pg_blocking_pids proves lock waits.
"""
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from unittest import skipUnless

from django.db import connection, connections, transaction
from django.test import TransactionTestCase

from inventory.models import Inventory
from .models import CheckoutRequest, OrderInfo, StockHold
from .reservations import ReservationError, close_order, confirm_payment
from .test_checkout_groups import CheckoutGroupFixtures


@skipUnless(connection.vendor == 'postgresql',
            'Requires PostgreSQL row locks and independent connections')
class CheckoutGroupConcurrencyTests(CheckoutGroupFixtures, TransactionTestCase):
    def setUp(self):
        self.seed_groups()

    def worker(self, action):
        connections.close_all()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '10s'")
                cursor.execute("SET statement_timeout = '15s'")
                cursor.execute('SELECT pg_backend_pid()')
                pid = cursor.fetchone()[0]
            try:
                return action(pid)
            except ReservationError as error:
                return error
        finally:
            connections.close_all()

    def assert_waiters_blocked_by(self, waiters, holder):
        deadline = time.monotonic() + 5
        poll = Event()
        chains = {}
        while time.monotonic() < deadline:
            with connection.cursor() as cursor:
                # PostgreSQL can report a queue predecessor as a soft blocker.
                # Follow real blocking edges for BOTH workers, independent of
                # which reaches the buyer row (or shared throttle row) first.
                # UNION deduplicates (waiter, pid), so cycles cannot recurse
                # indefinitely if a failure introduces an unexpected deadlock.
                cursor.execute('''
                    WITH RECURSIVE blockers(waiter, pid) AS (
                        SELECT pid, pid FROM unnest(%s::integer[]) AS worker(pid)
                        UNION
                        SELECT chain.waiter, blocked_by.pid
                        FROM blockers AS chain
                        CROSS JOIN LATERAL unnest(pg_blocking_pids(chain.pid))
                            AS blocked_by(pid)
                    )
                    SELECT waiter, array_agg(pid) FROM blockers GROUP BY waiter
                ''', [list(waiters)])
                chains = dict(cursor.fetchall())
                if all(holder in chains.get(waiter, []) for waiter in waiters):
                    return
            poll.wait(0.01)
        self.fail('Backends %s did not all block through backend %s; observed chains: %s'
                  % (waiters, holder, chains))

    def assert_limit_error(self, result):
        self.assertIsInstance(result, ReservationError)
        self.assertEqual((result.code, result.status), ('UNPAID_CHECKOUT_LIMIT', 429))
        self.assertEqual(result.details['pending_checkout_groups'], 3)
        self.assertEqual(result.details['max_unpaid_checkouts'], 3)

    def assert_inventory_consistent(self):
        for ledger in Inventory.objects.all():
            self.assertGreaterEqual(ledger.available_quantity, 0)
            self.assertEqual(ledger.quantity, ledger.available_quantity + ledger.reserved_quantity)
            held = sum(ledger.order_holds.filter(state__in=['reserved', 'paid'])
                       .values_list('quantity', flat=True))
            self.assertEqual(ledger.reserved_quantity, held)

    def test_two_requests_for_last_slot_allow_exactly_one_group(self):
        for sku in self.products[:2]:
            self.place_group(items={sku.pk: 1})
        barrier = Barrier(2)
        pids = []

        def attempt(sku):
            def run(pid):
                pids.append(pid)
                barrier.wait(timeout=10)
                return self.place_group(items={sku.pk: 1})
            return run

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(self.worker, attempt(sku)) for sku in self.products[2:4]]
            results = [future.result(timeout=20) for future in futures]
        self.assertEqual(len(set(pids)), 2)
        self.assertEqual(sum(isinstance(result, list) for result in results), 1, results)
        self.assert_limit_error(next(result for result in results if not isinstance(result, list)))
        self.assertEqual(len(self.active_group_keys()), 3)
        self.assertEqual((CheckoutRequest.objects.count(), OrderInfo.objects.count(), StockHold.objects.count()),
                         (3, 3, 3))
        self.assert_inventory_consistent()

    def lifecycle_race(self, payment):
        original = [self.place_group(items={sku.pk: 1})[0] for sku in self.products[:3]]
        target = original[0]
        locked, release = Event(), Event()
        started = [Event(), Event()]
        pids = {}

        def finish(pid):
            pids['finish'] = pid
            with transaction.atomic():
                if payment:
                    result = confirm_payment(target.pk, 'group-race-paid', target.total_amount)
                else:
                    result = close_order(target.pk, reason='merchant_cancel')
                locked.set()
                self.assertTrue(release.wait(10), 'Lifecycle transaction was not released')
            return result

        def checkout(index):
            def run(pid):
                pids[index] = pid
                started[index].set()
                return self.place_group(items={self.products[3 + index].pk: 1})
            return run

        with ThreadPoolExecutor(max_workers=3) as pool:
            finished = pool.submit(self.worker, finish)
            try:
                self.assertTrue(locked.wait(5), 'Lifecycle failed before locking buyer')
                pending = [pool.submit(self.worker, checkout(index)) for index in range(2)]
                self.assertTrue(started[0].wait(5))
                self.assertTrue(started[1].wait(5))
                self.assertEqual(len(set(pids.values())), 3)
                self.assert_waiters_blocked_by([pids[0], pids[1]], pids['finish'])
                # Other sessions still see the three committed old groups.
                self.assertEqual(len(self.active_group_keys()), 3)
            finally:
                release.set()
            self.assertIsInstance(finished.result(timeout=20), OrderInfo)
            results = [future.result(timeout=20) for future in pending]
        self.assertEqual(sum(isinstance(result, list) for result in results), 1, results)
        self.assert_limit_error(next(result for result in results if not isinstance(result, list)))
        self.assertEqual(len(self.active_group_keys()), 3)
        self.assertEqual(CheckoutRequest.objects.count(), 4)
        target.refresh_from_db()
        hold = StockHold.objects.get(item__order_info=target)
        self.assertEqual((target.status, hold.state), (2, 'paid') if payment else (0, 'released'))
        ledger = Inventory.objects.get(pk=hold.inventory_id)
        self.assertEqual(ledger.reserved_quantity, 1 if payment else 0)
        self.assert_inventory_consistent()

    def test_payment_racing_two_new_checkouts_does_not_exceed_three_groups(self):
        self.lifecycle_race(payment=True)

    def test_close_racing_two_new_checkouts_does_not_exceed_three_groups(self):
        self.lifecycle_race(payment=False)
