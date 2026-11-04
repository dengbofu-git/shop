"""PostgreSQL transaction and migration proofs; use an isolated test DB only."""
import hashlib
import json
import uuid
from datetime import timedelta
from importlib import import_module
from unittest import skipUnless
from unittest.mock import patch

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

from goods.models import SKU
from inventory.models import Inventory, InventoryLog, Warehouse
from .models import (
    CheckoutRequest, OrderGoods, OrderInfo, ReservationPolicy,
    ReservationRiskEvent, ReservationRiskState, StockHold,
)
from .reservations import (
    ReservationError, cancel_by_merchant, close_order, confirm_payment, expire_orders,
)
from .test_reservations import Fixtures


@skipUnless(connection.vendor == 'postgresql', 'Requires isolated PostgreSQL transactions')
class CheckoutRiskIntegrationTests(Fixtures, TransactionTestCase):
    def setUp(self):
        self.seed()
        self.started = timezone.now().replace(microsecond=0)
        self.warehouse = Warehouse.objects.create(name='Risk synthetic', code='RISK', address='Synthetic')
        self.groups = []
        for index in range(4):
            products = self.skus if index == 0 else [SKU.objects.create(
                spu=base.spu, name='Risk group %s' % index, price=10,
                market_price=12, cost_price=5, stock=100, is_launched=True,
            ) for base in self.skus]
            self.groups.append({sku.pk: 1 for sku in products})
            for sku in products:
                Inventory.objects.create(sku=sku, warehouse=self.warehouse, quantity=100)

    def timeout(self, orders):
        OrderInfo.objects.filter(pk__in=[order.pk for order in orders]).update(expires_at=self.started - timedelta(seconds=1))
        expire_orders(user_id=self.buyers[0].pk)

    def assert_refused(self, items):
        with self.assertRaises(ReservationError) as caught:
            self.place(items=items)
        self.assertEqual(caught.exception.code, 'RESERVATION_COOLDOWN')
        return caught.exception

    def test_three_multishop_groups_timeout_and_first_refusal_commits_fixed_state(self):
        with patch('orders.reservations.timezone.now', return_value=self.started):
            batches = [self.place(items=items) for items in self.groups[:3]]
            self.assertEqual([len(batch) for batch in batches], [2, 2, 2])
            self.timeout([order for batch in batches for order in batch])
            self.assertEqual(ReservationRiskEvent.objects.filter(kind='timeout').count(), 3)
            self.assertEqual(StockHold.objects.filter(state='released').count(), 6)
            self.assertFalse(connection.in_atomic_block)
            first = self.assert_refused(self.groups[3])
        state = ReservationRiskState.objects.get(user=self.buyers[0])
        self.assertEqual(state.cooldown_until, self.started + timedelta(seconds=1800))
        self.assertEqual((state.cooldown_kind, first.details['retry_after']), ('timeout', 1800))
        with patch('orders.reservations.timezone.now', return_value=self.started + timedelta(seconds=17)):
            refreshed = self.assert_refused(self.groups[3])
        state.refresh_from_db()
        self.assertEqual(refreshed.details['retry_after'], 1783)
        self.assertEqual(refreshed.details['cooldown_until'], first.details['cooldown_until'])
        self.assertEqual(state.cooldown_until, self.started + timedelta(seconds=1800))

    def test_partial_payment_preserves_paid_stock_but_remaining_timeout_still_counts(self):
        with patch('orders.reservations.timezone.now', return_value=self.started):
            paid, remaining = [], []
            for index, items in enumerate(self.groups[:3]):
                batch = self.place(items=items)
                confirm_payment(batch[0].pk, 'risk-part-paid-%s' % index, batch[0].total_amount)
                paid.append(batch[0])
                remaining.append(batch[1])
            self.timeout(remaining)
            self.assertEqual(ReservationRiskEvent.objects.filter(kind='timeout').count(), 3)
            self.assert_refused(self.groups[3])
        self.assertEqual(StockHold.objects.filter(state='paid').count(), 3)
        self.assertEqual(StockHold.objects.filter(state='released').count(), 3)
        self.assertEqual(OrderInfo.objects.filter(pk__in=[order.pk for order in paid], status=2).count(), 3)
        self.assertEqual(InventoryLog.objects.filter(log_type='release').count(), 3)

    def test_merchant_cancels_do_not_penalize_buyer(self):
        merchants = {merchant.pk: merchant for merchant in self.shops}
        with patch('orders.reservations.timezone.now', return_value=self.started):
            for items in self.groups[:3]:
                for order in self.place(items=items):
                    merchant = merchants[order.ordergoods_set.get().merchant_snapshot_id]
                    cancel_by_merchant(order.pk, merchant)
            self.assertFalse(ReservationRiskEvent.objects.exists())
            self.assertEqual(len(self.place(items=self.groups[3])), 2)
        self.assertEqual(OrderInfo.objects.filter(close_reason='merchant_cancel').count(), 6)
        self.assertIsNone(ReservationRiskState.objects.get(user=self.buyers[0]).cooldown_until)

    def test_stale_released_holds_without_a_new_release_never_create_penalties(self):
        for reason in ('user_cancel', 'expired'):
            with self.subTest(reason=reason):
                order = self.place()[0]
                close_order(order.pk, reason='merchant_cancel')
                # A historical inconsistent status must not turn already
                # released evidence into a new buyer abuse event.
                OrderInfo.objects.filter(pk=order.pk).update(
                    status=1, close_reason='', closed_at=None,
                    expires_at=timezone.now() - timedelta(seconds=1))
                before = list(Inventory.objects.order_by('pk').values())
                if reason == 'expired':
                    expire_orders(user_id=self.buyers[0].pk)
                else:
                    close_order(order.pk, self.buyers[0].pk)
                self.assertFalse(ReservationRiskEvent.objects.exists())
                self.assertEqual(list(Inventory.objects.order_by('pk').values()), before)

    def test_cooldown_allows_payment_cancellation_and_exact_idempotent_replay(self):
        key = uuid.uuid4().hex
        with patch('orders.reservations.timezone.now', return_value=self.started):
            existing = self.place(items=self.groups[0], key=key)
            for items in self.groups[1:]:
                self.timeout(self.place(items=items))
            refusal = self.assert_refused(self.groups[1])
            replayed = self.place(items=self.groups[0], key=key)
            self.assertEqual({order.pk for order in replayed}, {order.pk for order in existing})
            confirm_payment(existing[0].pk, 'risk-payment-in-cooldown', existing[0].total_amount)
            close_order(existing[1].pk, self.buyers[0].pk)
            refreshed = self.assert_refused(self.groups[1])
        existing[0].refresh_from_db()
        existing[1].refresh_from_db()
        self.assertEqual((existing[0].status, existing[1].status), (2, 0))
        self.assertEqual(ReservationRiskEvent.objects.filter(kind='cancel').count(), 1)
        self.assertEqual(refreshed.details['cooldown_until'], refusal.details['cooldown_until'])
        self.assertEqual(CheckoutRequest.objects.count(), 4)

    def test_invalid_sku_and_stock_failure_roll_back_without_risk_or_business_rows(self):
        before = list(Inventory.objects.order_by('pk').values())
        unknown = max(SKU.objects.values_list('pk', flat=True)) + 1000
        disabled = next(iter(self.groups[3]))
        SKU.objects.filter(pk=disabled).update(is_launched=False)
        cases = [
            ({self.skus[0].pk: 1, unknown: 1}, 'SKU_NOT_FOUND'),
            ({self.skus[0].pk: 1, disabled: 1}, 'PRODUCT_UNAVAILABLE'),
            ({self.skus[0].pk: 1, self.skus[1].pk: 101}, 'INSUFFICIENT_STOCK'),
        ]
        for items, code in cases:
            with self.subTest(code=code), self.assertRaises(ReservationError) as caught:
                self.place(items=items)
            self.assertEqual(caught.exception.code, code)
            self.assertFalse(ReservationRiskEvent.objects.exists())
            self.assertFalse(ReservationRiskState.objects.exists())
            self.assertFalse(CheckoutRequest.objects.exists())
            self.assertFalse(OrderInfo.objects.exists())
            self.assertFalse(StockHold.objects.exists())
            self.assertFalse(InventoryLog.objects.exists())
            self.assertEqual(list(Inventory.objects.order_by('pk').values()), before)


@skipUnless(connection.vendor == 'postgresql', 'Requires isolated PostgreSQL migrations')
class CheckoutRiskMigrationTests(Fixtures, TransactionTestCase):
    def setUp(self):
        executor = MigrationExecutor(connection)
        self.restore_targets = executor.loader.graph.leaf_nodes()
        self.addCleanup(self.restore_schema)
        executor.migrate([('orders', '0007_order_currency_snapshot')])
        self.seed()
        self.now = timezone.now()
        self.warehouse = Warehouse.objects.create(name='Migration synthetic', code='RISK-MIG', address='Synthetic')
        self.ledger = Inventory.objects.create(sku=self.skus[0], warehouse=self.warehouse, quantity=100)

    def restore_schema(self):
        MigrationExecutor(connection).migrate(self.restore_targets)

    def historical(self, name, checkout=None, reason='user_cancel', managed=True,
                   released=True, future=False, before_creation=False):
        created = self.now - timedelta(minutes=30)
        released_at = self.now - timedelta(minutes=20)
        if future:
            released_at = self.now + timedelta(days=1)
        if before_creation:
            released_at = created - timedelta(seconds=1)
        order = OrderInfo.objects.create(
            user_profile=self.buyers[0], order_id=name, checkout_request=checkout,
            total_amount=10, total_count=1, freight=0, status=0,
            reservation_managed=managed, expires_at=created + timedelta(minutes=10),
            closed_at=released_at + timedelta(seconds=1), close_reason=reason,
            receiver='Test', receiver_mobile='12345678901', address='Synthetic', tag='Test',
        )
        OrderInfo.objects.filter(pk=order.pk).update(created_time=created)
        item = OrderGoods.objects.create(order_info=order, sku=self.skus[0], count=1, price=10)
        StockHold.objects.create(item=item, inventory=self.ledger, quantity=1,
                                 state='released', released_at=released_at if released else None)
        return order

    @staticmethod
    def business_digest():
        # All original columns are compared, including deadlines, policy values,
        # inventory projections, timestamps, and historical purchase snapshots.
        payload = {model._meta.label: list(model.objects.order_by('pk').values())
                   for model in (CheckoutRequest, OrderInfo, OrderGoods, StockHold,
                                 Inventory, InventoryLog, ReservationPolicy, SKU)}
        return hashlib.sha256(json.dumps(payload, cls=DjangoJSONEncoder, sort_keys=True).encode()).hexdigest()

    def test_real_0007_to_0008_upgrade_backfills_only_proven_facts_without_business_writes(self):
        grouped = CheckoutRequest.objects.create(user=self.buyers[0], request_id='historical-group', fingerprint='synthetic')
        first = self.historical('history-cancel-a', checkout=grouped)
        self.historical('history-cancel-b', checkout=grouped)
        timeout_group = CheckoutRequest.objects.create(user=self.buyers[0], request_id='historical-timeout', fingerprint='synthetic')
        timeout = self.historical('history-timeout', checkout=timeout_group, reason='expired')
        legacy = self.historical('history-no-checkout', reason='expired')
        self.historical('history-unmanaged', managed=False)
        self.historical('history-merchant', reason='merchant_cancel')
        self.historical('history-unknown-release', released=False)
        self.historical('history-future', future=True)
        self.historical('history-before-creation', before_creation=True)
        before = self.business_digest()

        MigrationExecutor(connection).migrate([('orders', '0008_checkout_risk')])

        self.assertEqual(self.business_digest(), before)
        events = {event.group_key: event for event in ReservationRiskEvent.objects.all()}
        self.assertEqual(set(events), {'checkout:%s' % grouped.pk, 'checkout:%s' % timeout_group.pk, 'order:' + legacy.pk})
        self.assertEqual(events['checkout:%s' % grouped.pk].trigger_order_id, first.pk)
        self.assertEqual(events['checkout:%s' % grouped.pk].kind, 'cancel')
        self.assertEqual(events['checkout:%s' % timeout_group.pk].trigger_order_id, timeout.pk)
        self.assertEqual(events['order:' + legacy.pk].kind, 'timeout')
        self.assertEqual({event.occurred_at for event in events.values()}, {self.now - timedelta(minutes=20) + timedelta(seconds=1)})
        self.assertFalse(ReservationRiskState.objects.exists())
        migration = import_module('orders.migrations.0008_checkout_risk')
        with connection.schema_editor(atomic=False) as editor:
            migration.backfill_events(apps, editor)
            migration.backfill_events(apps, editor)
        self.assertEqual(ReservationRiskEvent.objects.count(), 3)
        self.assertEqual(self.business_digest(), before)
