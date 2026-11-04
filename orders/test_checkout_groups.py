"""Checkout groups, independently payable merchant orders and atomic admission.

These contracts run only on the isolated PostgreSQL test database. No new risk
models are imported here, so an incomplete implementation still collects.
"""
import uuid
from datetime import timedelta
from decimal import Decimal
from unittest import skipUnless
from unittest.mock import patch

from django.db import connection
from django.test import TestCase, override_settings
from django.utils import timezone

from goods.models import SKU, SPU
from inventory.models import Inventory, InventoryLog, Warehouse
from inventory.services import InventoryService
from users.models import UserProfile
from .models import (
    CartCleanupTask, CheckoutRequest, OrderGoods, OrderInfo, ReservationPolicy,
    StockHold,
)
from .reservations import ReservationError, close_order, confirm_payment, create_orders
from .test_reservations import Fixtures


class CheckoutGroupFixtures(Fixtures):
    def seed_groups(self):
        self.seed()
        # Raise only merchant quotas. Account defaults stay at 300 / CNY 60000.
        for index in range(2, 4):
            shop = UserProfile.objects.create(
                username='groupshop%s' % index, user_type='merchant', is_active=True)
            self.shops.append(shop)
            spu = SPU.objects.create(
                name='Group product %s' % index,
                catalog=self.skus[0].spu.catalog, merchant=shop)
            self.skus.append(SKU.objects.create(
                spu=spu, name='Group SKU %s' % index, price=10,
                market_price=12, cost_price=5, stock=1000, is_launched=True))
            ReservationPolicy.objects.create(merchant=shop)
        ReservationPolicy.objects.filter(merchant__in=self.shops).update(
            max_unpaid_quantity=1000, max_unpaid_amount=100000,
            max_stock_percent=100)
        self.products = list(self.skus)
        self.warehouse = Warehouse.objects.create(
            name='Synthetic group warehouse', code='GROUPS', address='Synthetic')
        for sku in self.products:
            Inventory.objects.create(sku=sku, warehouse=self.warehouse, quantity=1000)
        for index in range(4, 8):
            self.add_product(index)

    def add_product(self, index, merchant=0):
        sku = SKU.objects.create(
            spu=self.skus[merchant].spu, name='Group extra %s' % index,
            price=10, market_price=12, cost_price=5, stock=1000, is_launched=True)
        Inventory.objects.create(sku=sku, warehouse=self.warehouse, quantity=1000)
        self.products.append(sku)
        return sku

    def place_group(self, items=None, key=None, digest='same', snapshots=False):
        items = items if items is not None else {self.products[0].pk: 1}
        cart = {sid: {'generation': 'group-%s' % sid, 'version': 1,
                      'removed': 0, 'added': count}
                for sid, count in items.items()} if snapshots else None
        return create_orders(
            self.buyers[0], key or uuid.uuid4().hex, digest,
            self.addresses[0].pk, items, '198.51.100.41', cart_snapshots=cart)

    def active_group_keys(self):
        rows = OrderInfo.objects.filter(
            user_profile=self.buyers[0], reservation_managed=True, status=1,
            paid_at__isnull=True, expires_at__gt=timezone.now(),
            ordergoods__stock_holds__state='reserved').distinct()
        return {('checkout', row.checkout_request_id) if row.checkout_request_id
                else ('order', row.pk) for row in rows}

    def assert_group_limit(self, items):
        with self.assertRaises(ReservationError) as caught:
            self.place_group(items=items)
        error = caught.exception
        self.assertEqual((error.code, error.status), ('UNPAID_CHECKOUT_LIMIT', 429))
        self.assertEqual(error.details['pending_checkout_groups'], 3)
        self.assertEqual(error.details['max_unpaid_checkouts'], 3)


@skipUnless(connection.vendor == 'postgresql', 'Requires isolated PostgreSQL')
class CheckoutGroupTests(CheckoutGroupFixtures, TestCase):
    def setUp(self):
        self.seed_groups()

    def test_checkout_result_exposes_original_shop_snapshots_and_shared_deadline(self):
        from .checkout_views import result
        for index, shop in enumerate(self.shops):
            shop.shop_name = 'Original shop %s' % index
            shop.save(update_fields=['shop_name'])
        orders = self.place_group(items={sku.pk: 1 for sku in self.skus})
        UserProfile.objects.filter(pk__in=[shop.pk for shop in self.shops]).update(shop_name='Renamed later')
        data = result(orders)['data']
        self.assertEqual(data['checkout_id'], orders[0].checkout_request_id)
        self.assertEqual(data['checkout_expires_at'], orders[0].expires_at.isoformat())
        self.assertTrue(data['split_by_merchant'])
        for order, row in zip(orders, data['orders']):
            item = order.ordergoods_set.get()
            self.assertEqual(row['merchant_id'], item.merchant_snapshot_id)
            self.assertEqual(row['merchant_name'], item.purchase_snapshot['merchant_name'])
            self.assertNotEqual(row['merchant_name'], 'Renamed later')
            self.assertEqual(row['order_id'], order.pk)

    def test_direct_preview_reports_configured_group_cap_without_creating_a_group(self):
        from django.test import RequestFactory
        from .views import advance
        request = RequestFactory().get('/advance', {'settlement_type': '1',
            'sku_id': self.skus[0].pk, 'buy_num': 1})
        with override_settings(RESERVATION_MAX_UNPAID_CHECKOUTS=2), patch(
                'orders.checkout_views.buyer', return_value=self.buyers[0]):
            import json
            data = json.loads(advance(request, self.buyers[0].username).content)['data']
        self.assertEqual(data['max_unpaid_checkouts'], 2)
        self.assertFalse(CheckoutRequest.objects.exists())

    def test_four_merchants_form_one_group_with_independent_orders_and_one_deadline(self):
        started = timezone.now().replace(microsecond=0)
        items = {sku.pk: index + 1 for index, sku in enumerate(self.skus)}
        with patch('orders.reservations.timezone.now', return_value=started):
            orders = self.place_group(items=items, snapshots=True)
        self.assertEqual(len(orders), 4)
        self.assertEqual(len({order.pk for order in orders}), 4)
        self.assertEqual(len({order.checkout_request_id for order in orders}), 1)
        self.assertEqual({order.expires_at for order in orders},
                         {started + timedelta(seconds=900)})
        self.assertEqual(len(self.active_group_keys()), 1)
        for order in orders:
            item = order.ordergoods_set.get()
            sku = item.sku
            self.assertEqual(item.merchant_snapshot_id, sku.spu.merchant_id)
            self.assertEqual(item.purchase_snapshot['merchant_id'], sku.spu.merchant_id)
            self.assertEqual((order.total_count, order.total_amount),
                             (items[sku.pk], Decimal('10') * items[sku.pk]))
        paid, cancelled = orders[:2]
        confirm_payment(paid.pk, 'group-four-paid', paid.total_amount)
        close_order(cancelled.pk, self.buyers[0].pk)
        self.assertEqual(StockHold.objects.get(item__order_info=paid).state, 'paid')
        self.assertEqual(StockHold.objects.get(item__order_info=cancelled).state, 'released')
        self.assertEqual(OrderInfo.objects.filter(pk__in=[o.pk for o in orders[2:]], status=1).count(), 2)
        self.assertEqual(CartCleanupTask.objects.count(), 4)

    def test_three_different_sku_checkouts_succeed_and_fourth_reports_groups(self):
        for sku in self.products[:3]:
            self.place_group(items={sku.pk: 1})
        self.assertEqual(len(self.active_group_keys()), 3)
        self.assert_group_limit({self.products[3].pk: 1})
        self.assertEqual(CheckoutRequest.objects.count(), 3)

    @override_settings(RESERVATION_MAX_HOLD_SECONDS_PER_HOUR=1,
                       RESERVATION_MAX_UNPAID_ORDERS=1)
    def test_retired_duration_and_child_order_settings_do_not_limit_groups(self):
        orders = self.place_group(items={sku.pk: 1 for sku in self.skus})
        self.assertEqual(len(orders), 4)
        self.assertEqual(len(self.active_group_keys()), 1)

    def test_same_sku_cannot_be_reserved_again_under_another_group(self):
        self.place_group()
        with self.assertRaises(ReservationError) as caught:
            self.place_group()
        self.assertEqual(caught.exception.code, 'SKU_ALREADY_RESERVED')
        self.assertEqual(CheckoutRequest.objects.count(), 1)

    def test_partial_payment_and_cancel_keep_one_group_until_last_unpaid_hold_leaves(self):
        orders = self.place_group(items={sku.pk: 1 for sku in self.skus})
        for sku in self.products[4:6]:
            self.place_group(items={sku.pk: 1})
        paid = orders[0]
        confirm_payment(paid.pk, 'partial-group-paid', paid.total_amount)
        close_order(orders[1].pk, self.buyers[0].pk)
        self.assertEqual(len(self.active_group_keys()), 3)
        self.assert_group_limit({self.products[6].pk: 1})
        close_order(orders[2].pk, self.buyers[0].pk)
        self.assertEqual(len(self.active_group_keys()), 3)
        confirm_payment(orders[3].pk, 'last-group-paid', orders[3].total_amount)
        self.assertEqual(len(self.active_group_keys()), 2)
        self.place_group(items={self.products[6].pk: 1})
        hold = StockHold.objects.get(item__order_info=paid)
        self.assertEqual((hold.state, hold.quantity), ('paid', 1))
        ledger = Inventory.objects.get(pk=hold.inventory_id)
        self.assertEqual((ledger.quantity, ledger.reserved_quantity, ledger.available_quantity),
                         (1000, 1, 999))

    def test_all_paid_group_releases_slot_without_releasing_paid_stock(self):
        orders = self.place_group(items={sku.pk: 1 for sku in self.skus})
        for order in orders:
            confirm_payment(order.pk, 'all-paid-' + order.pk, order.total_amount)
        self.assertEqual(len(self.active_group_keys()), 0)
        self.assertEqual(StockHold.objects.filter(state='paid').count(), 4)
        for sku in self.products[4:7]:
            self.place_group(items={sku.pk: 1})
        self.assertEqual(len(self.active_group_keys()), 3)

    def test_all_merchant_cancelled_group_releases_slot(self):
        orders = self.place_group(items={sku.pk: 1 for sku in self.skus})
        for order in orders:
            close_order(order.pk, reason='merchant_cancel')
        self.assertEqual(len(self.active_group_keys()), 0)
        for sku in self.products[4:7]:
            self.place_group(items={sku.pk: 1})
        self.assertEqual(StockHold.objects.filter(state='released').count(), 4)

    def test_null_checkout_managed_orders_are_individual_groups_and_not_rewritten(self):
        orders = self.place_group(items={sku.pk: 1 for sku in self.skus[:3]})
        ids = [order.pk for order in orders]
        OrderInfo.objects.filter(pk__in=ids).update(checkout_request=None)
        before = list(OrderInfo.objects.filter(pk__in=ids).order_by('pk').values())
        self.assertEqual(len(self.active_group_keys()), 3)
        self.assert_group_limit({self.products[3].pk: 1})
        self.assertEqual(list(OrderInfo.objects.filter(pk__in=ids).order_by('pk').values()), before)
        close_order(orders[0].pk, reason='merchant_cancel')
        self.place_group(items={self.products[3].pk: 1})
        self.assertEqual(len(self.active_group_keys()), 3)
        self.assertEqual(OrderInfo.objects.filter(pk__in=ids, checkout_request=None).count(), 3)

    def test_legacy_orders_without_stock_holds_do_not_use_group_slots(self):
        for index in range(4):
            order = OrderInfo.objects.create(
                user_profile=self.buyers[0], order_id='unreserved-legacy-%s' % index,
                total_amount=10, total_count=1, freight=0, status=1,
                receiver='Test', receiver_mobile='12345678901', address='Synthetic', tag='Test')
            OrderGoods.objects.create(order_info=order, sku=self.products[7], count=1, price=10)
        for sku in self.products[:3]:
            self.place_group(items={sku.pk: 1})
        self.assertEqual(len(self.active_group_keys()), 3)
        self.assert_group_limit({self.products[3].pk: 1})
        self.assertEqual(OrderInfo.objects.filter(reservation_managed=False, status=1).count(), 4)

    def test_managed_pending_rows_without_any_reserved_hold_do_not_use_group_slots(self):
        for index in range(4):
            OrderInfo.objects.create(
                user_profile=self.buyers[0], order_id='managed-without-hold-%s' % index,
                total_amount=10, total_count=1, freight=0, status=1,
                reservation_managed=True, expires_at=timezone.now() + timedelta(seconds=900),
                receiver='Test', receiver_mobile='12345678901', address='Synthetic', tag='Test')
        for sku in self.products[:3]:
            self.place_group(items={sku.pk: 1})
        self.assertEqual(len(self.active_group_keys()), 3)
        self.assert_group_limit({self.products[3].pk: 1})

    def test_replay_at_full_capacity_never_adds_group_or_extends_deadline(self):
        key = uuid.uuid4().hex
        orders = self.place_group(items={sku.pk: 1 for sku in self.skus}, key=key)
        expiry = {order.pk: order.expires_at for order in orders}
        for sku in self.products[4:6]:
            self.place_group(items={sku.pk: 1})
        with patch('orders.reservations.timezone.now', return_value=timezone.now() + timedelta(seconds=30)):
            replay = self.place_group(items={sku.pk: 1 for sku in self.skus}, key=key)
        self.assertEqual({order.pk: order.expires_at for order in replay}, expiry)
        with self.assertRaises(ReservationError) as caught:
            self.place_group(items={sku.pk: 1 for sku in self.skus}, key=key, digest='changed')
        self.assertEqual(caught.exception.code, 'IDEMPOTENCY_CONFLICT')
        self.assertEqual(CheckoutRequest.objects.count(), 3)
        self.assertEqual(len(self.active_group_keys()), 3)

    def test_quantity_and_amount_limits_accumulate_across_groups(self):
        self.place_group(items={self.products[0].pk: 150})
        self.place_group(items={self.products[1].pk: 150})
        with self.assertRaises(ReservationError) as caught:
            self.place_group(items={self.products[2].pk: 1})
        self.assertEqual(caught.exception.code, 'UNPAID_QUANTITY_LIMIT')
        self.assertEqual(CheckoutRequest.objects.count(), 2)

    def test_default_account_amount_limit_is_60000_across_groups(self):
        SKU.objects.filter(pk__in=[s.pk for s in self.products[:3]]).update(price=30000)
        self.place_group(items={self.products[0].pk: 1})
        self.place_group(items={self.products[1].pk: 1})
        with self.assertRaises(ReservationError) as caught:
            self.place_group(items={self.products[2].pk: 1})
        self.assertEqual(caught.exception.code, 'UNPAID_AMOUNT_LIMIT')
        self.assertEqual(CheckoutRequest.objects.count(), 2)

    def test_merchant_quantity_and_amount_quotas_still_accumulate_across_groups(self):
        self.place_group(items={self.products[0].pk: 2})
        policy = ReservationPolicy.objects.get(merchant=self.shops[0])
        for fields in ({'max_unpaid_quantity': 3, 'max_unpaid_amount': 100000},
                       {'max_unpaid_quantity': 1000, 'max_unpaid_amount': 30}):
            ReservationPolicy.objects.filter(pk=policy.pk).update(**fields)
            with self.subTest(fields=fields), self.assertRaises(ReservationError) as caught:
                self.place_group(items={self.products[4].pk: 2})
            self.assertEqual(caught.exception.code, 'BULK_CONFIRMATION_REQUIRED')
        self.assertEqual(CheckoutRequest.objects.count(), 1)

    def test_merchant_stock_percentage_guard_remains(self):
        ReservationPolicy.objects.filter(merchant=self.shops[0]).update(max_stock_percent=1)
        with self.assertRaises(ReservationError) as caught:
            self.place_group(items={self.products[0].pk: 11})
        self.assertEqual(caught.exception.code, 'BULK_CONFIRMATION_REQUIRED')
        self.assertFalse(CheckoutRequest.objects.exists())

    def test_stock_quantity_and_amount_rejections_leave_no_partial_group_or_cleanup(self):
        for kind in ('stock', 'quantity', 'amount'):
            SKU.objects.filter(pk=self.products[1].pk).update(price=10)
            items = {self.products[0].pk: 1, self.products[1].pk: 1}
            if kind == 'stock':
                Inventory.objects.filter(sku=self.products[1]).update(quantity=0, available_quantity=0)
                expected = 'INSUFFICIENT_STOCK'
            elif kind == 'quantity':
                Inventory.objects.filter(sku=self.products[1]).update(quantity=1000, available_quantity=1000)
                items[self.products[1].pk] = 300
                expected = 'UNPAID_QUANTITY_LIMIT'
            else:
                SKU.objects.filter(pk=self.products[1].pk).update(price=60000)
                expected = 'UNPAID_AMOUNT_LIMIT'
            with self.subTest(kind=kind), self.assertRaises(ReservationError) as caught:
                self.place_group(items=items, snapshots=True)
            self.assertEqual(caught.exception.code, expected)
            for model in (CheckoutRequest, OrderInfo, OrderGoods, StockHold, CartCleanupTask, InventoryLog):
                self.assertEqual(model.objects.count(), 0, model.__name__)
            self.assertFalse(Inventory.objects.exclude(reserved_quantity=0).exists())

    def test_failure_after_first_merchant_hold_rolls_back_entire_checkout(self):
        create_hold = StockHold.objects.create
        calls = []

        def fail_second(**kwargs):
            calls.append(kwargs)
            if len(calls) == 2:
                raise ReservationError('INSUFFICIENT_STOCK', 'Synthetic competing stock change')
            return create_hold(**kwargs)

        with patch.object(StockHold.objects, 'create', side_effect=fail_second):
            with self.assertRaises(ReservationError):
                self.place_group(items={sku.pk: 1 for sku in self.skus}, snapshots=True)
        self.assertEqual(len(calls), 2)
        for model in (CheckoutRequest, OrderInfo, OrderGoods, StockHold, CartCleanupTask, InventoryLog):
            self.assertEqual(model.objects.count(), 0, model.__name__)
        self.assertFalse(Inventory.objects.exclude(reserved_quantity=0).exists())

    def test_twenty_skus_across_four_merchants_succeed_but_twenty_one_is_rejected_early(self):
        for index in range(8, 21):
            self.add_product(index, merchant=index % 4)
        with patch('orders.reservations.expire_orders') as expire, patch.object(
                InventoryService, 'locked_ledgers', wraps=InventoryService.locked_ledgers) as lock:
            with self.assertRaises(ReservationError) as caught:
                self.place_group(items={sku.pk: 1 for sku in self.products}, snapshots=True)
        self.assertEqual(caught.exception.code, 'CHECKOUT_SKU_LIMIT')
        self.assertEqual(caught.exception.details['checkout_sku_limit'], 20)
        expire.assert_not_called()
        lock.assert_not_called()
        self.assertFalse(CheckoutRequest.objects.exists())
        orders = self.place_group(items={sku.pk: 1 for sku in self.products[:20]})
        self.assertEqual((len(orders), OrderGoods.objects.count()), (4, 20))
        self.assertEqual(len(self.active_group_keys()), 1)
