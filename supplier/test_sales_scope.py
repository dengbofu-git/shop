"""Merchant sales completeness uses real, scoped orders without rewriting them."""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from goods.models import Catalog, SKU, SPU
from orders.models import OrderGoods, OrderInfo, PreSaleOrder, TrialOrder
from tea_saas.utils import jwt_encode
from users.models import UserProfile

from .analytics import build_supplier_analytics
from .insights import build_supplier_insights


class MerchantSalesScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = UserProfile.objects.create(username='sc-buyer', is_active=True)
        cls.shop = UserProfile.objects.create(username='sc-shop', user_type='merchant', is_active=True)
        cls.other = UserProfile.objects.create(username='sc-other', user_type='merchant', is_active=True)
        catalog = Catalog.objects.create(name='Scope tea')
        cls.products = [SPU.objects.create(name=shop.username, merchant=shop, catalog=catalog)
                        for shop in (cls.shop, cls.other)]
        cls.skus = [SKU.objects.create(name=product.name, spu=product, price=10,
                                      cost_price=5, market_price=12)
                    for product in cls.products]

    def setUp(self):
        self.now = timezone.make_aware(datetime(2026, 11, 3, 12))

    def order(self, key, *, currency='CNY', status=2, kind='standard', lines=None, created=None):
        order = OrderInfo.objects.create(
            order_id=key, user_profile=self.buyer, order_type=kind, status=status,
            total_amount='999.99', total_count=9, freight='99.99', currency=currency,
            receiver='Synthetic', address='Synthetic', receiver_mobile='000', tag='Test')
        for sku, quantity, price in lines or [(self.skus[0], 1, '10.00')]:
            OrderGoods.objects.create(order_info=order, sku=sku, count=quantity, price=Decimal(price))
        OrderInfo.objects.filter(pk=order.pk).update(
            created_time=created or self.now - timedelta(days=1))
        return order

    def reports(self, user=None, period='year'):
        user = user or self.shop
        with patch('supplier.analytics.timezone.localtime', return_value=self.now):
            analytics = build_supplier_analytics(user, period)
        return analytics, build_supplier_insights(user, now=self.now)

    def assert_scopes(self, reports, expected):
        analytics, insights = reports
        self.assertIn('sales_scope', analytics['summary'])
        self.assertIn('sales_scope', insights)
        self.assertEqual(analytics['summary']['sales_scope'], expected)
        self.assertEqual(insights['sales_scope'], expected)

    def test_94_eligible_legacy_null_orders_are_unavailable_including_27_completed(self):
        for status, count in [(2, 29), (3, 38), (4, 27), (1, 10), (0, 3)]:
            for index in range(count):
                self.order('legacy-%s-%s' % (status, index), currency=None, status=status)
        reports = self.reports()
        self.assert_scopes(reports, {
            'currency': 'CNY', 'status_order_count': 94, 'cny_order_count': 0,
            'unknown_currency_order_count': 94, 'other_currency_order_count': 0,
            'financial_state': 'unavailable',
        })
        summary = reports[0]['summary']
        self.assertEqual((summary['order_count'], summary['completed']), (107, 27))
        self.assertEqual((summary['total_sales'], summary['paid_order_count'], summary['avg_order_amount']),
                         (0.0, 0, 0))
        self.assertIsInstance(summary['total_sales'], float)
        self.assertEqual(reports[1]['totals'], {'amount': '0.00', 'quantity': 0, 'paid_orders': 0})

    def test_mixed_currencies_count_distinct_own_orders_and_preserve_cny_line_totals(self):
        self.order('mixed-cny', lines=[(self.skus[0], 3, '.10'), (self.skus[0], 1, '.20'),
                                       (self.skus[1], 1, '900')])
        self.order('mixed-null', currency=None,
                   lines=[(self.skus[0], 2, '100'), (self.skus[0], 1, '200'), (self.skus[1], 1, '300')])
        self.order('usd', currency='USD')
        self.order('blank', currency='')
        self.order('external', currency=None, lines=[(self.skus[1], 1, '999')])
        reports = self.reports()
        self.assert_scopes(reports, {
            'currency': 'CNY', 'status_order_count': 4, 'cny_order_count': 1,
            'unknown_currency_order_count': 2, 'other_currency_order_count': 1,
            'financial_state': 'partial',
        })
        summary = reports[0]['summary']
        self.assertEqual((summary['total_sales'], summary['paid_order_count'], summary['avg_order_amount']),
                         (0.5, 1, 0.5))
        self.assertIsInstance(summary['total_sales'], float)
        self.assertIsInstance(summary['avg_order_amount'], float)
        self.assertEqual(summary['total_sales_display'], '¥0.50')
        self.assertEqual(reports[1]['totals'], {'amount': '0.50', 'quantity': 4, 'paid_orders': 1})

    def test_foreign_currency_only_is_unavailable_without_inventing_unknown_currency(self):
        self.order('usd-only', currency='USD')
        self.order('eur-only', currency='EUR')
        self.assert_scopes(self.reports(), {
            'currency': 'CNY', 'status_order_count': 2, 'cny_order_count': 0,
            'unknown_currency_order_count': 0, 'other_currency_order_count': 2,
            'financial_state': 'unavailable',
        })

    def test_empty_shop_and_unpaid_only_have_complete_zero_sales_scope(self):
        expected = {
            'currency': 'CNY', 'status_order_count': 0, 'cny_order_count': 0,
            'unknown_currency_order_count': 0, 'other_currency_order_count': 0,
            'financial_state': 'complete',
        }
        self.assert_scopes(self.reports(), expected)
        self.order('unpaid-null', currency=None, status=1)
        self.order('closed-usd', currency='USD', status=0)
        self.assert_scopes(self.reports(), expected)

    def test_cny_only_has_complete_scope_and_does_not_depend_on_line_currency(self):
        cny = self.order('cny-only')
        OrderGoods.objects.filter(order_info=cny).update(currency=None)
        self.assert_scopes(self.reports(), {
            'currency': 'CNY', 'status_order_count': 1, 'cny_order_count': 1,
            'unknown_currency_order_count': 0, 'other_currency_order_count': 0,
            'financial_state': 'complete',
        })

    def test_zero_priced_cny_sale_with_excluded_order_is_partial_and_preserves_real_zero_amounts(self):
        self.order('zero-cny', lines=[(self.skus[0], 2, '0.00')])
        self.order('unknown-price', currency=None)
        reports = self.reports()
        self.assert_scopes(reports, {
            'currency': 'CNY', 'status_order_count': 2, 'cny_order_count': 1,
            'unknown_currency_order_count': 1, 'other_currency_order_count': 0,
            'financial_state': 'partial',
        })
        summary = reports[0]['summary']
        self.assertEqual((summary['total_sales'], summary['paid_order_count'], summary['avg_order_amount']),
                         (0.0, 1, 0.0))
        self.assertIsInstance(summary['total_sales'], float)
        self.assertIsInstance(summary['avg_order_amount'], float)
        self.assertEqual(summary['total_sales_display'], '¥0.00')
        self.assertEqual(reports[1]['totals'], {'amount': '0.00', 'quantity': 2, 'paid_orders': 1})

    def test_scope_uses_original_subtype_sales_rules_before_classifying_currency(self):
        for status, currency in [(2, 'CNY'), (3, None), (4, ''), (0, 'USD'), (1, None)]:
            self.order('standard-%s' % status, status=status, currency=currency)
        for status in range(1, 9):
            trial = self.order('trial-%s' % status, kind='trial', status=1, currency=None)
            TrialOrder.objects.create(order_info=trial, status=status)
        for key, status, deposit, balance in [
            ('full', 4, True, True), ('complete', 6, True, True), ('cancel', 7, True, True),
            ('deposit', 2, True, False), ('unpaid', 1, False, False), ('no-deposit', 4, False, True),
        ]:
            order = self.order('presale-' + key, kind='presale', status=1, currency='USD')
            PreSaleOrder.objects.create(order_info=order, status=status, deposit_amount=2,
                                       balance_amount=8, deposit_paid=deposit, balance_paid=balance)
        reports = self.reports()
        self.assert_scopes(reports, {
            'currency': 'CNY', 'status_order_count': 11, 'cny_order_count': 1,
            'unknown_currency_order_count': 8, 'other_currency_order_count': 2,
            'financial_state': 'partial',
        })
        self.assertEqual(reports[0]['summary']['paid_order_count'], 1)
        self.assertEqual(reports[1]['totals']['paid_orders'], 1)

    def test_purchase_snapshot_precedes_current_owner_and_null_snapshot_uses_legacy_owner(self):
        self.order('recorded-null', currency=None)
        legacy = self.order('legacy-usd', currency='USD')
        OrderGoods.objects.filter(order_info=legacy).update(merchant_snapshot=None)
        SPU.objects.filter(pk=self.products[0].pk).update(merchant=self.other)
        self.assert_scopes(self.reports(), {
            'currency': 'CNY', 'status_order_count': 1, 'cny_order_count': 0,
            'unknown_currency_order_count': 1, 'other_currency_order_count': 0,
            'financial_state': 'unavailable',
        })
        self.assert_scopes(self.reports(self.other), {
            'currency': 'CNY', 'status_order_count': 1, 'cny_order_count': 0,
            'unknown_currency_order_count': 0, 'other_currency_order_count': 1,
            'financial_state': 'unavailable',
        })

    def test_each_analytics_period_limits_scope_by_its_existing_lower_boundary(self):
        for key, days, currency in [('recent', 1, 'CNY'), ('month-start', 30, None),
                                    ('quarter-start', 92, ''), ('year-start', 365, 'USD'),
                                    ('too-old', 366, None)]:
            self.order(key, currency=currency, created=self.now - timedelta(days=days))
        expected = {
            'month': {'currency': 'CNY', 'status_order_count': 2, 'cny_order_count': 1,
                      'unknown_currency_order_count': 1, 'other_currency_order_count': 0,
                      'financial_state': 'partial'},
            'quarter': {'currency': 'CNY', 'status_order_count': 3, 'cny_order_count': 1,
                        'unknown_currency_order_count': 2, 'other_currency_order_count': 0,
                        'financial_state': 'partial'},
            'year': {'currency': 'CNY', 'status_order_count': 4, 'cny_order_count': 1,
                     'unknown_currency_order_count': 2, 'other_currency_order_count': 1,
                     'financial_state': 'partial'},
        }
        for period, scope in expected.items():
            with self.subTest(period=period):
                summary = self.reports(period=period)[0]['summary']
                self.assertIn('sales_scope', summary)
                self.assertEqual(summary['sales_scope'], scope)
        self.assert_scopes(self.reports(), expected['year'])

    def test_insights_excludes_end_and_future_while_analytics_retains_existing_no_upper_bound(self):
        for key, created, currency in [
            ('start', self.now - timedelta(days=365), None),
            ('too-old', self.now - timedelta(days=365, seconds=1), None),
            ('end', self.now, 'CNY'), ('future', self.now + timedelta(days=1), 'USD'),
        ]:
            self.order(key, currency=currency, created=created)
        analytics, insights = self.reports()
        self.assertIn('sales_scope', analytics['summary'])
        self.assertEqual(analytics['summary']['sales_scope'], {
            'currency': 'CNY', 'status_order_count': 3, 'cny_order_count': 1,
            'unknown_currency_order_count': 1, 'other_currency_order_count': 1,
            'financial_state': 'partial',
        })
        self.assertIn('sales_scope', insights)
        self.assertEqual(insights['sales_scope'], {
            'currency': 'CNY', 'status_order_count': 1, 'cny_order_count': 0,
            'unknown_currency_order_count': 1, 'other_currency_order_count': 0,
            'financial_state': 'unavailable',
        })

    def test_reporting_performs_only_selects_and_preserves_order_and_line_values(self):
        self.order('read-only-null', currency=None)
        self.order('read-only-usd', currency='USD')
        before_orders = list(OrderInfo.objects.order_by('pk').values())
        before_lines = list(OrderGoods.objects.order_by('pk').values())
        with CaptureQueriesContext(connection) as queries:
            reports = self.reports()
        self.assert_scopes(reports, {
            'currency': 'CNY', 'status_order_count': 2, 'cny_order_count': 0,
            'unknown_currency_order_count': 1, 'other_currency_order_count': 1,
            'financial_state': 'unavailable',
        })
        self.assertTrue(queries.captured_queries)
        for query in queries.captured_queries:
            self.assertTrue(query['sql'].lstrip().upper().startswith('SELECT'), query['sql'])
        self.assertEqual(list(OrderInfo.objects.order_by('pk').values()), before_orders)
        self.assertEqual(list(OrderGoods.objects.order_by('pk').values()), before_lines)

    def test_endpoints_expose_scope_at_existing_payload_locations(self):
        self.order('api-unknown', currency=None)
        self.order('api-foreign-shop', currency='USD', lines=[(self.skus[1], 1, '900')])
        token = jwt_encode({'id': self.shop.pk, 'username': self.shop.username})
        if isinstance(token, bytes):
            token = token.decode()
        with patch('supplier.analytics.timezone.localtime', return_value=self.now):
            analytics = self.client.get('/v1/supplier/analytics?period=year',
                                        HTTP_AUTHORIZATION='Bearer ' + token)
            insights = self.client.get('/v1/supplier/insights?merchant_id=%s' % self.other.pk,
                                       HTTP_AUTHORIZATION='Bearer ' + token)
        self.assertEqual(analytics.status_code, 200)
        self.assertEqual(insights.status_code, 200)
        self.assert_scopes((analytics.json()['data'], insights.json()['data']), {
            'currency': 'CNY', 'status_order_count': 1, 'cny_order_count': 0,
            'unknown_currency_order_count': 1, 'other_currency_order_count': 0,
            'financial_state': 'unavailable',
        })
