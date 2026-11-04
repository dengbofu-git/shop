"""Platform expiry applies to new checkouts without rewriting merchant history."""
import uuid
from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from goods.models import SPU, SKU
from inventory.models import Inventory
from users.models import UserProfile
from .models import CheckoutRequest, OrderInfo, ReservationPolicy, ReservationPolicyChange, StockHold
from .reservations import policy_for
from .test_reservations import Fixtures


class CheckoutPolicyTests(Fixtures, TestCase):
    def setUp(self):
        self.seed()

    def test_existing_600_and_custom_300_and_missing_policy_all_create_900_second_orders(self):
        for ttl in (600, 300, None):
            with self.subTest(configured=ttl):
                ReservationPolicy.objects.filter(merchant=self.shops[0]).delete()
                if ttl is not None:
                    ReservationPolicy.objects.create(merchant=self.shops[0], ttl_seconds=ttl)
                order = self.place(buyer=(600, 300, None).index(ttl), items={self.skus[0].pk:1})[0]
                self.assertAlmostEqual((order.expires_at-order.created_time).total_seconds(), 900, delta=1)
                saved = ReservationPolicy.objects.filter(merchant=self.shops[0]).first()
                self.assertEqual(saved.ttl_seconds if saved else None, ttl)

    def test_effective_policy_is_an_independent_immutable_snapshot_with_merchant_limits(self):
        configured = ReservationPolicy.objects.get(merchant=self.shops[0])
        configured.ttl_seconds = 300
        configured.max_unpaid_quantity = 17
        configured.max_unpaid_amount = Decimal('123.45')
        configured.max_stock_percent = 23
        configured.save()
        snapshot = policy_for(self.shops[0].pk)
        self.assertEqual(snapshot.ttl_seconds, 900)
        self.assertEqual(getattr(snapshot, 'configured_ttl_seconds', None), 300)
        self.assertEqual(getattr(snapshot, 'ttl_source', None), 'platform_fixed_900_v1')
        self.assertIs(getattr(snapshot, 'ttl_editable', None), False)
        self.assertEqual((snapshot.max_unpaid_quantity, snapshot.max_unpaid_amount, snapshot.max_stock_percent),
                         (17, Decimal('123.45'), 23))
        with self.assertRaises((FrozenInstanceError, AttributeError)):
            snapshot.ttl_seconds = 600
        configured.max_unpaid_quantity = 99
        configured.save()
        self.assertEqual(snapshot.max_unpaid_quantity, 17)

    def test_existing_order_deadline_and_replay_are_not_extended(self):
        key = uuid.uuid4().hex
        order = self.place(key=key)[0]
        old_deadline = order.created_time+timedelta(seconds=600)
        OrderInfo.objects.filter(pk=order.pk).update(expires_at=old_deadline)
        ReservationPolicy.objects.filter(merchant=self.shops[0]).update(ttl_seconds=300)
        replayed = self.place(key=key)[0]
        self.assertEqual(replayed.pk, order.pk)
        self.assertEqual(replayed.expires_at, old_deadline)
        self.assertEqual(StockHold.objects.count(), 1)

    def test_two_merchants_share_one_900_second_deadline_and_checkout_group(self):
        orders = self.place(items={sku.pk:1 for sku in self.skus})
        self.assertEqual(len(orders), 2)
        self.assertEqual(len({order.checkout_request_id for order in orders}), 1)
        self.assertEqual(len({order.expires_at for order in orders}), 1)
        for order in orders:
            self.assertAlmostEqual((order.expires_at-order.created_time).total_seconds(), 900, delta=1)

    def test_three_merchants_create_one_group_without_summing_child_order_duration(self):
        merchant = UserProfile.objects.create(username='thirdshop', user_type='merchant', is_active=True)
        spu = SPU.objects.create(name='Third', catalog=self.skus[0].spu.catalog, merchant=merchant)
        third = SKU.objects.create(spu=spu, name='Third', price=10, market_price=12, cost_price=5,
                                   stock=100, is_launched=True)
        ReservationPolicy.objects.create(merchant=merchant, max_stock_percent=100,
                                         max_unpaid_quantity=300)
        orders = self.place(items={sku.pk:1 for sku in self.skus+[third]})
        self.assertEqual(len(orders), 3)
        self.assertEqual(len({order.checkout_request_id for order in orders}), 1)
        self.assertEqual(len({order.expires_at for order in orders}), 1)
        self.assertEqual(CheckoutRequest.objects.count(), 1)
        self.assertEqual(StockHold.objects.count(), 3)
        self.assertEqual(Inventory.objects.filter(reserved_quantity=1).count(), 3)

    def test_old_order_deadline_is_preserved_without_duration_budget_affecting_new_group(self):
        first = self.place()[0]
        now = timezone.now()
        for seconds in (600, 900, 901, 1801):
            with self.subTest(old_committed_seconds=seconds), transaction.atomic():
                OrderInfo.objects.filter(pk=first.pk).update(created_time=now, expires_at=now+timedelta(seconds=seconds))
                with patch('orders.reservations.timezone.now', return_value=now):
                    orders = self.place(items={self.skus[1].pk:1})
                self.assertEqual(len(orders), 1)
                self.assertEqual(orders[0].expires_at, now+timedelta(seconds=900))
                self.assertNotEqual(orders[0].checkout_request_id, first.checkout_request_id)
                self.assertEqual(OrderInfo.objects.get(pk=first.pk).expires_at,
                                 now+timedelta(seconds=seconds))
                transaction.set_rollback(True)


class CheckoutPolicyApiTests(Fixtures, TestCase):
    url = '/v1/supplier/reservation-policy'

    def setUp(self):
        self.seed()
        self.data = {'ttl_seconds':900, 'max_unpaid_quantity':90, 'max_unpaid_amount':'9000',
                     'max_stock_percent':40, 'change_reason':'按本周供货计划调整额度'}

    def get_policy(self):
        return self.client.get(self.url, **self.headers(self.shops[0]))

    def put_policy(self, **changes):
        return self.client.put(self.url, {**self.data, **changes}, content_type='application/json',
                               **self.headers(self.shops[0]))

    def test_get_reports_effective_and_configured_values_without_writing(self):
        for ttl in (600, 300, None):
            with self.subTest(configured=ttl):
                ReservationPolicy.objects.filter(merchant=self.shops[0]).delete()
                if ttl is not None:
                    ReservationPolicy.objects.create(merchant=self.shops[0], ttl_seconds=ttl)
                response = self.get_policy()
                self.assertEqual(response.status_code, 200)
                data = response.json()['data']
                self.assertEqual(data['ttl_seconds'], 900)
                self.assertEqual(data['configured_ttl_seconds'], ttl)
                self.assertEqual(data['ttl_source'], 'platform_fixed_900_v1')
                self.assertIs(data['ttl_editable'], False)
                self.assertEqual(ReservationPolicy.objects.filter(merchant=self.shops[0]).exists(), ttl is not None)
                self.assertFalse(ReservationPolicyChange.objects.exists())

    def test_non_900_ttl_is_rejected_without_policy_or_audit_write(self):
        ReservationPolicy.objects.filter(merchant=self.shops[0]).delete()
        for ttl in (60, 300, 600, 899, 901, True):
            with self.subTest(ttl=ttl):
                self.assertEqual(self.put_policy(ttl_seconds=ttl).status_code, 400)
                self.assertFalse(ReservationPolicy.objects.filter(merchant=self.shops[0]).exists())
                self.assertFalse(ReservationPolicyChange.objects.exists())

    def test_explicit_update_preserves_legacy_ttl_and_audits_effective_source(self):
        response = self.put_policy()
        self.assertEqual(response.status_code, 200)
        configured = ReservationPolicy.objects.get(merchant=self.shops[0])
        self.assertEqual(configured.ttl_seconds, 600)
        self.assertEqual((configured.max_unpaid_quantity, configured.max_unpaid_amount, configured.max_stock_percent),
                         (90, Decimal('9000'), 40))
        audit = ReservationPolicyChange.objects.get()
        self.assertEqual((audit.actor_id, audit.merchant_id, audit.reason),
                         (self.shops[0].pk, self.shops[0].pk, self.data['change_reason']))
        self.assertEqual(audit.before['max_unpaid_quantity'], 300)
        self.assertEqual(audit.after['max_unpaid_quantity'], 90)
        self.assertEqual((audit.before['max_unpaid_amount'], audit.before['max_stock_percent']), ('20000.00', 100))
        self.assertEqual((audit.after['max_unpaid_amount'], audit.after['max_stock_percent']), ('9000.00', 40))
        for value in (audit.before, audit.after, response.json()['data']):
            self.assertEqual(value['ttl_seconds'], 900)
            self.assertEqual(value['configured_ttl_seconds'], 600)
            self.assertEqual(value['ttl_source'], 'platform_fixed_900_v1')
            self.assertIs(value['ttl_editable'], False)

    def test_explicit_update_creates_missing_policy_at_900(self):
        ReservationPolicy.objects.filter(merchant=self.shops[0]).delete()
        self.assertEqual(self.put_policy().status_code, 200)
        self.assertEqual(ReservationPolicy.objects.get(merchant=self.shops[0]).ttl_seconds, 900)
        self.assertEqual(ReservationPolicyChange.objects.get().actor_id, self.shops[0].pk)

    def test_audit_failure_rolls_back_limit_update(self):
        with patch('orders.checkout_views.ReservationPolicyChange.objects.create', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError):
                self.put_policy()
        configured = ReservationPolicy.objects.get(merchant=self.shops[0])
        self.assertEqual((configured.ttl_seconds, configured.max_unpaid_quantity), (600, 300))
        self.assertFalse(ReservationPolicyChange.objects.exists())
