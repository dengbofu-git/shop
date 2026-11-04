"""Checkout-group event accounting and fixed, persisted admission cooldowns."""
from datetime import timedelta
from importlib import import_module

from django.apps import apps
from django.db import connection, transaction
from django.test import TestCase
from django.utils import timezone

from . import models
from .test_reservations import Fixtures


class CheckoutRiskTests(Fixtures, TestCase):
    def setUp(self):
        self.seed()
        self.now = timezone.now()

    def api(self):
        # A missing implementation produces an explicit RED assertion, not a
        # module import failure that prevents unrelated suites from collecting.
        self.assertTrue(hasattr(models, 'ReservationRiskEvent'), 'persistent group risk events are missing')
        self.assertTrue(hasattr(models, 'ReservationRiskState'), 'persistent cooldown state is missing')
        return import_module('orders.checkout_risk')

    def event(self, kind, index, at=None):
        order = models.OrderInfo.objects.create(
            user_profile=self.buyers[0], order_id='risk-%s-%s' % (kind, index),
            total_amount=10, total_count=1, freight=0, status=0,
            receiver='Test', receiver_mobile='12345678901', address='Synthetic', tag='Test',
        )
        return models.ReservationRiskEvent.objects.create(
            user=self.buyers[0], group_key='order:' + order.pk, kind=kind,
            occurred_at=at or self.now, trigger_order=order,
        )

    def check(self, at=None):
        api = self.api()
        with transaction.atomic():
            type(self.buyers[0]).objects.select_for_update().get(pk=self.buyers[0].pk)
            return api.check_admission(self.buyers[0], at or self.now)

    def test_three_timeouts_start_fixed_cooldown_and_refresh_does_not_extend_it(self):
        self.api()
        for index in range(3):
            self.event('timeout', index)
        error = self.check()
        self.assertEqual((error.code, error.status, error.details['retry_after']), ('RESERVATION_COOLDOWN', 429, 1800))
        self.assertEqual(error.details['cooldown_reason'], 'timeout')
        refreshed = self.check(self.now + timedelta(seconds=19, microseconds=1))
        self.assertEqual(refreshed.details['retry_after'], 1781)
        self.assertEqual(refreshed.details['cooldown_until'], error.details['cooldown_until'])
        self.assertIsNone(self.check(self.now + timedelta(seconds=1800)))

    def test_cancel_threshold_then_second_trigger_within_day_escalates(self):
        self.api()
        for index in range(4):
            self.event('cancel', index)
        self.assertIsNone(self.check())
        self.event('cancel', 4)
        self.assertEqual(self.check().details['retry_after'], 600)
        later = self.now + timedelta(seconds=601)
        for index in range(5, 10):
            self.event('cancel', index, later)
        self.assertEqual(self.check(later).details['retry_after'], 1800)
        self.assertIsNone(self.check(later + timedelta(seconds=1800)))

    def test_cancel_escalation_resets_after_day_and_old_events_are_ignored(self):
        self.api()
        for index in range(5):
            self.event('cancel', index, self.now - timedelta(hours=2))
        self.assertIsNone(self.check())
        for index in range(5, 10):
            self.event('cancel', index)
        self.assertEqual(self.check().details['retry_after'], 600)
        later = self.now + timedelta(days=1, seconds=1)
        for index in range(10, 15):
            self.event('cancel', index, later)
        self.assertEqual(self.check(later).details['retry_after'], 600)

    def test_timeout_precedes_cancel_and_different_buyers_are_independent(self):
        self.api()
        for index in range(3):
            self.event('timeout', index)
        for index in range(5):
            self.event('cancel', index)
        self.assertEqual(self.check().details['cooldown_reason'], 'timeout')
        with transaction.atomic():
            self.assertIsNone(self.api().check_admission(self.buyers[1], self.now))

    def test_multishop_release_counts_once_per_kind_and_needs_released_stock(self):
        api = self.api()
        orders = self.place(items={sku.pk: 1 for sku in self.skus})
        self.assertEqual(len(orders), 2)
        self.assertEqual(api.group_key(orders[0]), 'checkout:%s' % orders[0].checkout_request_id)
        self.assertEqual(api.group_key(orders[0]), api.group_key(orders[1]))
        with transaction.atomic():
            self.assertIsNone(api.record_release(orders[0], 'user_cancel', self.now))
            models.StockHold.objects.filter(item__order_info__in=orders).update(state='released', released_at=self.now)
            first = api.record_release(orders[0], 'user_cancel', self.now)
            duplicate = api.record_release(orders[1], 'user_cancel', self.now + timedelta(seconds=5))
            self.assertEqual(first.pk, duplicate.pk)
            self.assertEqual(duplicate.occurred_at, self.now)
            self.assertIsNone(api.record_release(orders[1], 'merchant_cancel', self.now))
            api.record_release(orders[1], 'expired', self.now)
        self.assertEqual(models.ReservationRiskEvent.objects.count(), 2)

    def test_legacy_without_checkout_is_separate_and_unmanaged_release_is_ignored(self):
        api = self.api()
        order = self.place()[0]
        order.checkout_request = None
        order.save(update_fields=['checkout_request'])
        self.assertEqual(api.group_key(order), 'order:' + order.pk)
        models.StockHold.objects.filter(item__order_info=order).update(state='released', released_at=self.now)
        order.reservation_managed = False
        with transaction.atomic():
            self.assertIsNone(api.record_release(order, 'expired', self.now))

    def test_backfill_requires_trustworthy_release_and_is_repeatable(self):
        self.api()
        migration = import_module('orders.migrations.0008_checkout_risk')
        orders = self.place(items={sku.pk: 1 for sku in self.skus})
        at = self.now - timedelta(minutes=1)
        models.OrderInfo.objects.filter(pk__in=[order.pk for order in orders]).update(created_time=at - timedelta(minutes=1))
        models.StockHold.objects.filter(item__order_info=orders[0]).update(state='released', released_at=at)
        models.OrderInfo.objects.filter(pk__in=[order.pk for order in orders]).update(status=0, closed_at=at, close_reason='user_cancel')
        with connection.schema_editor(atomic=False) as editor:
            migration.backfill_events(apps, editor)
            migration.backfill_events(apps, editor)
        event = models.ReservationRiskEvent.objects.get()
        self.assertEqual((event.kind, event.occurred_at, event.trigger_order_id), ('cancel', at, orders[0].pk))
        # Missing released_at, merchant closes and unmanaged rows never supply evidence.
        models.StockHold.objects.filter(item__order_info=orders[1]).update(state='released', released_at=None)
        models.OrderInfo.objects.filter(pk=orders[1].pk).update(checkout_request=None)
        with connection.schema_editor(atomic=False) as editor:
            migration.backfill_events(apps, editor)
        self.assertEqual(models.ReservationRiskEvent.objects.count(), 1)
        future = self.now + timedelta(days=1)
        models.StockHold.objects.filter(item__order_info=orders[1]).update(released_at=future)
        models.OrderInfo.objects.filter(pk=orders[1].pk).update(closed_at=future)
        with connection.schema_editor(atomic=False) as editor:
            migration.backfill_events(apps, editor)
        self.assertEqual(models.ReservationRiskEvent.objects.count(), 1)
        models.StockHold.objects.filter(item__order_info=orders[1]).update(released_at=at - timedelta(days=1))
        models.OrderInfo.objects.filter(pk=orders[1].pk).update(closed_at=at)
        with connection.schema_editor(atomic=False) as editor:
            migration.backfill_events(apps, editor)
        self.assertEqual(models.ReservationRiskEvent.objects.count(), 1)
