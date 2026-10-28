"""Real sales aggregation, without fabricated market data or cross-shop totals."""
from datetime import datetime, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from goods.models import Catalog, SKU, SPU
from orders.models import OrderGoods, OrderInfo, PreSaleOrder, TrialOrder
from tea_saas.utils import jwt_encode
from users.models import Role, UserProfile, UserRole
from .insights import build_supplier_insights


class SupplierInsightsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = UserProfile.objects.create(username='ins-buyer', is_active=True)
        cls.shop = UserProfile.objects.create(username='ins-shop', user_type='merchant', is_active=True)
        cls.other = UserProfile.objects.create(username='ins-other', user_type='merchant', is_active=True)
        catalog = Catalog.objects.create(name='测试茶')
        cls.products = [SPU.objects.create(name=name, merchant=shop, catalog=catalog)
                        for shop, name in [(cls.shop, '真实茶品'), (cls.shop, '同名商品'), (cls.other, '外店茶品')]]
        cls.skus = [SKU.objects.create(name='默认规格', spu=product, price=999, cost_price=1, market_price=999)
                    for product in cls.products]

    def order(self, key, *, lines=None, kind='standard', status=2, created=None):
        order = OrderInfo.objects.create(order_id=key, user_profile=self.buyer, order_type=kind,
            status=status, total_amount=9999, total_count=9, freight=999, receiver='私密姓名',
            address='私密地址', receiver_mobile='00000000000', tag='测试')
        for sku, count, price in lines or [(self.skus[0], 1, '10.00')]:
            OrderGoods.objects.create(order_info=order, sku=sku, count=count, price=Decimal(price))
        # Keep ordinary fixtures strictly inside the reporting window. Windows
        # clocks may give creation and query the same timestamp; end is exclusive.
        OrderInfo.objects.filter(pk=order.pk).update(created_time=created or timezone.now() - timedelta(days=1))
        return order

    def get(self, user, query=''):
        token = jwt_encode({'id': user.pk, 'username': user.username})
        if isinstance(token, bytes):
            token = token.decode()
        return self.client.get('/v1/supplier/insights' + query, HTTP_AUTHORIZATION='Bearer ' + token)

    def test_mixed_order_sums_own_historical_prices_and_distinct_paid_orders(self):
        self.order('mixed', lines=[(self.skus[0], 3, '0.10'), (self.skus[1], 1, '0.20'), (self.skus[2], 1, '900.00')])
        response = self.get(self.shop, '?merchant_id=' + str(self.other.pk))
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['totals'], dict(amount='0.50', quantity=4, paid_orders=1))
        self.assertEqual(data['price_distribution']['quantity'], 4)
        self.assertNotContains(response, '私密')
        self.assertNotContains(response, '外店茶品')
        self.assertNotContains(response, 'receiver_mobile')
        self.assertIn('no-store', response['Cache-Control'])

    def test_shared_full_payment_rules_exclude_unpaid_returned_and_cancelled(self):
        self.order('paid')
        self.order('unpaid', status=1)
        for status in (2, 6, 7, 8):
            TrialOrder.objects.create(order_info=self.order('trial-' + str(status), kind='trial'), status=status)
        for key, status, deposit, balance in [('full', 4, True, True), ('deposit', 2, True, False), ('cancel', 7, True, True)]:
            PreSaleOrder.objects.create(order_info=self.order(key, kind='presale'), status=status,
                deposit_amount=2, balance_amount=8, deposit_paid=deposit, balance_paid=balance)
        data = build_supplier_insights(self.shop)
        self.assertEqual(data['totals'], dict(amount='50.00', quantity=5, paid_orders=5))
        self.assertEqual(sum(row['order_count'] for row in data['monthly']), 5)

    def test_variants_group_by_product_and_quantity_ranking_differs_from_revenue(self):
        variant = SKU.objects.create(name='另一规格', spu=self.products[0], price=999, cost_price=1, market_price=999)
        self.order('ranking', lines=[(self.skus[0], 3, '2'), (variant, 2, '2'), (self.skus[1], 1, '100')])
        data = build_supplier_insights(self.shop)
        self.assertEqual([row['quantity'] for row in data['top_products']], [5, 1])
        self.assertEqual([row['name'] for row in data['top_products']], ['真实茶品', '同名商品'])
        self.assertEqual([row['amount'] for row in data['sales_top_products']], ['100.00', '10.00'])

    def test_same_named_products_remain_separate_with_deterministic_ties(self):
        SPU.objects.filter(pk=self.products[0].pk).update(name='同名商品')
        self.order('names', lines=[(self.skus[0], 1, '10'), (self.skus[1], 1, '10')])
        rows = build_supplier_insights(self.shop)['top_products']
        self.assertEqual(len(rows), 2)
        self.assertEqual([row['product_id'] for row in rows], [self.products[0].pk, self.products[1].pk])

    def test_price_boundaries_do_not_overlap_and_percentages_use_units(self):
        lines = [(self.skus[0], qty, price) for qty, price in
                 [(1, '0'), (1, '79.99'), (2, '80'), (2, '119.99'), (1, '120'), (1, '279.99'), (2, '280')]]
        self.order('prices', lines=lines)
        data = build_supplier_insights(self.shop)['price_distribution']
        self.assertEqual(data['quantity'], 10)
        self.assertEqual([row['quantity'] for row in data['buckets']], [2, 4, 2, 2])
        self.assertEqual([row['percent'] for row in data['buckets']], [20, 40, 20, 20])
        self.assertEqual(sum(row['quantity'] for row in data['buckets']), data['quantity'])

    def test_invalid_price_samples_are_excluded_and_disclosed_only_for_distribution(self):
        self.order('invalid', lines=[(self.skus[0], 3, '80'), (self.skus[0], 0, '20'), (self.skus[0], 1, '-1')])
        data = build_supplier_insights(self.shop)['price_distribution']
        self.assertEqual(data['quantity'], 3)
        self.assertEqual(data['excluded_lines'], 2)
        self.assertEqual(data['buckets'][1]['percent'], 100)

    def test_365_day_interval_includes_start_but_excludes_end_and_future(self):
        now = timezone.make_aware(datetime(2026, 10, 22, 12))
        for key, created in [('start', now - timedelta(days=365)), ('too-old', now - timedelta(days=365, seconds=1)),
                              ('end', now), ('future', now + timedelta(days=1))]:
            self.order(key, created=created)
        self.assertEqual(build_supplier_insights(self.shop, now=now)['totals']['paid_orders'], 1)

    def test_months_use_calendar_boundaries_years_and_current_partial_month(self):
        now = timezone.make_aware(datetime(2026, 3, 31, 12))
        for key, date in [('jan', datetime(2026, 1, 31, 23, 59)), ('feb', datetime(2026, 2, 1, 0)),
                          ('march', datetime(2026, 3, 1, 0))]:
            self.order(key, created=timezone.make_aware(date))
        rows = build_supplier_insights(self.shop, now=now)['monthly']
        self.assertEqual([row['month'] for row in rows], ['2025-10','2025-11','2025-12','2026-01','2026-02','2026-03'])
        self.assertEqual([row['order_count'] for row in rows], [0,0,0,1,1,1])
        self.assertEqual([row['amount'] for row in rows][-3:], ['10.00'] * 3)

    def test_recorded_merchant_wins_over_product_transfer_with_legacy_fallback(self):
        self.order('recorded')
        legacy = self.order('legacy')
        OrderGoods.objects.filter(order_info=legacy).update(merchant_snapshot=None)
        SPU.objects.filter(pk=self.products[0].pk).update(merchant=self.other)
        self.assertEqual(build_supplier_insights(self.shop)['totals']['paid_orders'], 1)
        self.assertEqual(build_supplier_insights(self.other)['totals']['paid_orders'], 1)

    def test_empty_shop_returns_real_zero_empty_rankings_and_unavailable_nulls(self):
        data = build_supplier_insights(self.other)
        self.assertEqual(data['totals'], dict(amount='0.00', quantity=0, paid_orders=0))
        self.assertEqual(data['top_products'], [])
        self.assertEqual(data['sales_top_products'], [])
        self.assertEqual([row['percent'] for row in data['price_distribution']['buckets']], [None] * 4)
        self.assertEqual(sum(row['order_count'] for row in data['monthly']), 0)
        self.assertIsNone(data['taste_preferences'])
        self.assertIsNone(data['regional_sales'])
        self.assertEqual(data['industry'], dict(export_trend=None, competitors=None, policies=None))

    def test_top_lists_cap_at_five(self):
        for i in range(7):
            spu = SPU.objects.create(name='商品%d' % i, merchant=self.shop, catalog=self.products[0].catalog)
            sku = SKU.objects.create(name='规格', spu=spu, price=10, cost_price=5, market_price=12)
            self.order('cap%d' % i, lines=[(sku, i+1, '10')])
        data = build_supplier_insights(self.shop)
        self.assertEqual(len(data['top_products']), 5)
        self.assertEqual([row['quantity'] for row in data['top_products']], [7,6,5,4,3])

    def test_endpoint_denies_wrong_method_anonymous_customer_inactive_and_platform(self):
        self.assertEqual(self.client.post('/v1/supplier/insights').status_code, 405)
        self.assertEqual(self.client.get('/v1/supplier/insights').status_code, 401)
        self.assertEqual(self.get(self.buyer).status_code, 403)
        self.other.is_active = False
        self.other.save()
        self.assertEqual(self.get(self.other).status_code, 401)
        role = Role.objects.create(code='admin', name='平台管理员')
        UserRole.objects.create(user_profile=self.shop, role=role)
        self.assertEqual(self.get(self.shop).status_code, 403)
