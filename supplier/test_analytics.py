"""Compare merchant sales to the platform using synthetic, isolated orders."""
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from admin_panel.analytics import build_platform_overview
from tea_saas.utils import jwt_encode
from goods.models import Catalog, SKU, SPU
from orders.models import OrderGoods, OrderInfo, PreSaleOrder, TrialOrder
from users.models import UserProfile

from .analytics import build_supplier_analytics


class MerchantSalesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = UserProfile.objects.create(username='testbuyer', password='unused', is_active=True)
        cls.merchant = UserProfile.objects.create(username='testshop', password='unused',
                                                   user_type='merchant', is_active=True)
        cls.other = UserProfile.objects.create(username='othershop', password='unused',
                                                user_type='merchant', is_active=True)
        catalog = Catalog.objects.create(name='测试茶')
        cls.skus = []
        for merchant in (cls.merchant, cls.other):
            spu = SPU.objects.create(name=merchant.username, merchant=merchant, catalog=catalog)
            cls.skus.append(SKU.objects.create(name=merchant.username, spu=spu, price=10,
                                               cost_price=5, market_price=12))

    def order(self, key, amount='100.00', *, kind='standard', status=2, lines=None):
        order = OrderInfo.objects.create(
            order_id=key, user_profile=self.buyer, total_amount=Decimal(amount), total_count=1,
            freight=Decimal('5.00'), order_type=kind, status=status, receiver='测试',
            address='测试地址', receiver_mobile='00000000000', tag='测试')
        for sku, qty, price in lines or [(self.skus[0], 1, amount)]:
            OrderGoods.objects.create(order_info=order, sku=sku, count=qty, price=Decimal(price))
        return order

    def test_unpaid_is_excluded_from_every_sales_aggregate(self):
        self.order('paid')
        self.order('unpaid', '900.00', status=1)
        result = build_supplier_analytics(self.merchant)
        summary = result['summary']
        self.assertEqual(summary['total_sales'], 100)
        self.assertEqual(summary['total_sales_display'], '¥100.00')
        self.assertEqual(summary['order_count'], 2)
        self.assertEqual(summary['paid_order_count'], 1)
        self.assertEqual(summary['avg_order_amount'], 100)
        for key, amount_key in [('monthly', 'sales'), ('categories', 'sales'),
                                ('regions', 'sales'), ('top_products', 'amount')]:
            self.assertEqual(sum(row[amount_key] for row in result[key]), 100, key)
        self.assertEqual(build_platform_overview()['summary']['total_sales'], '100.00')

    def test_mixed_merchant_order_only_counts_own_lines(self):
        self.order('mixed', lines=[(self.skus[0], 2, '30.00'), (self.skus[1], 1, '40.00')])
        result = build_supplier_analytics(self.merchant)
        other = build_supplier_analytics(self.other)
        self.assertEqual(result['summary']['total_sales'], 60)
        self.assertEqual(other['summary']['total_sales'], 40)
        self.assertEqual(result['recent_orders'][0]['amount'], 60)
        self.assertEqual(result['recent_orders'][0]['count'], 2)
        self.assertEqual(Decimal(str(result['summary']['total_sales']))
                         + Decimal(str(other['summary']['total_sales'])),
                         Decimal(build_platform_overview()['summary']['total_sales']))

    def test_trial_and_presale_share_platform_payment_rules(self):
        for status, amount in [(2, '80.00'), (7, '999.00'), (8, '20.00')]:
            order = self.order('trial-' + str(status), amount, kind='trial')
            TrialOrder.objects.create(order_info=order, status=status)
        for key, status, deposit, balance in [('full', 4, True, True),
                                              ('deposit', 2, True, False),
                                              ('cancelled', 7, True, True)]:
            order = self.order('presale-' + key, '200.00', kind='presale')
            PreSaleOrder.objects.create(order_info=order, status=status, deposit_amount=50,
                                       balance_amount=150, deposit_paid=deposit, balance_paid=balance)
        summary = build_supplier_analytics(self.merchant)['summary']
        self.assertEqual(summary['total_sales'], 300)
        self.assertEqual(summary['paid_order_count'], 3)
        self.assertEqual(build_platform_overview()['summary']['total_sales'], '300.00')

    def test_period_only_limits_merchant_history_and_does_not_inflate_sales(self):
        order = self.order('older', '200.00')
        OrderInfo.objects.filter(pk=order.pk).update(created_time=timezone.now() - timedelta(days=60))
        self.order('new', '100.00')
        self.assertEqual(build_supplier_analytics(self.merchant, 'month')['summary']['total_sales'], 100)
        self.assertEqual(build_supplier_analytics(self.merchant, 'year')['summary']['total_sales'], 300)
        self.assertEqual(build_platform_overview()['summary']['total_sales'], '300.00')

    def test_month_buckets_are_unique_across_year_and_short_month(self):
        now = timezone.make_aware(datetime(2026, 3, 31, 12))
        for key, date, amount in [('jan', datetime(2026, 1, 31, 23), '10.10'),
                                   ('feb', datetime(2026, 2, 1, 0), '20.20')]:
            order = self.order(key, amount)
            OrderInfo.objects.filter(pk=order.pk).update(created_time=timezone.make_aware(date))
        with patch('supplier.analytics.timezone.localtime', return_value=now):
            result = build_supplier_analytics(self.merchant)
        months = {row['month']: row for row in result['monthly']}
        self.assertEqual(list(months), ['2025-10', '2025-11', '2025-12', '2026-01', '2026-02', '2026-03'])
        self.assertEqual(months['2026-01']['sales'], 10.10)
        self.assertEqual(months['2026-02']['sales'], 20.20)

    def test_unpaid_only_and_empty_shop_do_not_fabricate_sales(self):
        self.order('unpaid', '999.00', status=1)
        for user in (self.merchant, self.other):
            summary = build_supplier_analytics(user)['summary']
            self.assertEqual(summary['total_sales'], 0)
            self.assertEqual(summary['paid_order_count'], 0)
            self.assertEqual(summary['avg_order_amount'], 0)

    def test_endpoint_returns_merchant_scoped_paid_sales(self):
        self.order('paid')
        self.order('other', '900.00', lines=[(self.skus[1], 1, '900.00')])
        token = jwt_encode({'id': self.merchant.pk, 'username': self.merchant.username})
        if isinstance(token, bytes):
            token = token.decode()
        response = self.client.get('/v1/supplier/analytics?period=year', HTTP_AUTHORIZATION=token)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['summary']['total_sales'], 100)
        self.assertIn('不含运费', response.json()['data']['sales_basis'])

    def test_fulfillment_metrics_use_order_states(self):
        for status in (1, 2, 3, 4):
            self.order('fulfillment-' + str(status), status=status)
        result = build_supplier_analytics(self.merchant)
        summary = result['summary']
        self.assertEqual(summary['completion_rate'], 25.0)
        self.assertEqual(summary['in_transit'], 1)
        self.assertEqual(summary['completed'], 1)
        self.assertNotIn('customs_in_transit', summary)
        self.assertNotIn('compliance_pass_rate', summary)
        self.assertNotIn('logistics_days', result)
        self.assertEqual(build_supplier_analytics(self.other)['summary']['completion_rate'], 0)
