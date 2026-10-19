"""Platform statistics and access tests on an isolated database."""
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from tea_saas.utils import jwt_encode
from orders.models import OrderInfo, PreSaleOrder, TrialOrder
from users.models import Permission, Role, RolePermission, UserProfile, UserRole

from .analytics import build_platform_overview


class PlatformOverviewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_rbac', verbosity=0)
        UserProfile.objects.all().delete()
        cls.operator = cls.user('statadmin', 'customer', 'super_admin')
        cls.buyer = cls.user('statbuyer', 'customer', 'buyer')
        cls.merchant = cls.user('statshop', 'merchant', 'supplier')

    @staticmethod
    def user(name, kind, role):
        user = UserProfile.objects.create(username=name, user_type=kind, password='unused',
                                          email=name + '@example.test', phone='', is_active=True)
        UserRole.objects.create(user_profile=user, role=Role.objects.get(code=role))
        return user

    def headers(self, user):
        token = jwt_encode({'id': user.pk, 'username': user.username})
        if isinstance(token, bytes):
            token = token.decode()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + token}

    def order(self, key, amount='100.00', kind='standard', status=2, freight='5.00'):
        return OrderInfo.objects.create(
            order_id=key, user_profile=self.buyer, total_amount=Decimal(amount), total_count=1,
            freight=Decimal(freight), order_type=kind, status=status, receiver='测试',
            address='测试地址', receiver_mobile='00000000000', tag='测试')

    def test_empty_orders_are_zero_and_all_days_are_present(self):
        OrderInfo.objects.all().delete()
        result = build_platform_overview()
        self.assertEqual(result['summary']['total_sales'], '0.00')
        self.assertEqual(result['summary']['total_flow'], '0.00')
        self.assertEqual(len(result['daily']), 30)
        self.assertTrue(all(row['sales'] == '0.00' for row in result['daily']))
        self.assertEqual(result['daily'][-1]['date'], timezone.localdate().isoformat())

    def test_standard_trial_and_presale_have_distinct_money_and_status_rules(self):
        OrderInfo.objects.all().delete()
        self.order('standard-paid')
        self.order('standard-unpaid', '999.00', status=1)
        returned = self.order('trial-returned', '40.00', 'trial')
        TrialOrder.objects.create(order_info=returned, status=7)
        in_trial = self.order('trial-active', '80.10', 'trial')
        TrialOrder.objects.create(order_info=in_trial, status=4)
        deposit = self.order('presale-deposit', '200.00', 'presale')
        PreSaleOrder.objects.create(order_info=deposit, status=2, deposit_amount=50,
                                   balance_amount=150, deposit_paid=True)
        paid = self.order('presale-paid', '200.00', 'presale')
        PreSaleOrder.objects.create(order_info=paid, status=4, deposit_amount=50,
                                   balance_amount=150, deposit_paid=True, balance_paid=True)
        cancelled = self.order('presale-cancelled', '200.00', 'presale')
        PreSaleOrder.objects.create(order_info=cancelled, status=7, deposit_amount=50,
                                   balance_amount=150, deposit_paid=True)
        result = build_platform_overview()
        self.assertEqual(result['summary']['total_sales'], '380.10')
        self.assertEqual(result['summary']['total_flow'], '535.10')
        self.assertEqual(result['summary']['order_count'], 7)
        self.assertEqual(result['summary']['paid_order_count'], 3)
        self.assertEqual(sum(row['count'] for row in result['states']), 7)
        self.assertEqual(result['daily'][-1]['flow'], '535.10')
        self.assertEqual(result['summary']['buyer_count'], 1)
        self.assertEqual(result['summary']['merchant_count'], 1)

    def test_trend_uses_local_creation_day_and_excludes_older_orders(self):
        OrderInfo.objects.all().delete()
        order = self.order('old-paid')
        OrderInfo.objects.filter(pk=order.pk).update(created_time=timezone.now() - timedelta(days=31))
        # 16:30 UTC is the next day in Asia/Shanghai.
        now = timezone.now().astimezone(timezone.get_current_timezone()).replace(hour=0, minute=30)
        today_order = self.order('local-midnight', '0.10', freight='0.20')
        OrderInfo.objects.filter(pk=today_order.pk).update(created_time=now)
        result = build_platform_overview()
        self.assertEqual(result['summary']['total_sales'], '100.10')
        self.assertEqual(result['daily'][-1]['sales'], '0.10')
        self.assertEqual(sum(row['order_count'] for row in result['daily']), 1)

    def test_inactive_platform_role_does_not_hide_an_active_business_account(self):
        role = Role.objects.get(code='finance')
        role.is_active = False
        role.save(update_fields=['is_active'])
        UserRole.objects.create(user_profile=self.buyer, role=role)
        self.assertEqual(build_platform_overview()['summary']['buyer_count'], 1)

    def test_unknown_order_status_is_preserved_in_distribution(self):
        OrderInfo.objects.all().delete()
        self.order('missing-status', status=None)
        result = build_platform_overview()
        self.assertEqual(result['states'][-1], {'name': '其他 / 状态缺失', 'count': 1})
        self.assertEqual(result['summary']['total_sales'], '0.00')

    def test_overview_requires_platform_role_and_data_permission(self):
        url = '/v1/admin-panel/overview'
        self.assertEqual(self.client.get(url).status_code, 401)
        for user in (self.buyer, self.merchant):
            self.assertEqual(self.client.get(url, **self.headers(user)).status_code, 403)
        RolePermission.objects.create(role=Role.objects.get(code='supplier'),
                                      permission=Permission.objects.get(code='data_view'))
        self.assertEqual(self.client.get(url, **self.headers(self.merchant)).status_code, 403)
        headers = self.headers(self.operator)
        response = self.client.get(url, **headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Cache-Control'], 'no-store')
        self.assertEqual(self.client.post(url, **headers).status_code, 405)
        RolePermission.objects.filter(role__code='super_admin', permission__code='data_view').delete()
        self.assertEqual(self.client.get(url, **headers).status_code, 403)

    def test_database_failure_does_not_return_fake_zero_statistics(self):
        with patch('admin_panel.views.build_platform_overview', side_effect=RuntimeError('test-only')):
            with self.assertLogs('admin_panel.views', level='ERROR'):
                response = self.client.get('/v1/admin-panel/overview', **self.headers(self.operator))
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('data', response.json())

    def test_navigation(self):
        page = self.client.get('/admin_panel.html')
        for label in ('交易总览', 'Agent 管理', '账号管理'):
            self.assertContains(page, label)
        overview = self.client.get('/admin_panel.html')
        self.assertNotContains(overview, 'id="user-username"')
        self.assertNotContains(overview, '提交知识库文件')
        self.assertContains(overview, 'id="platform-workspace"')
        self.assertContains(self.client.get('/admin_users.html?embedded=1'), 'id="user-username"')
        self.assertNotContains(self.client.get('/admin_agents.html?embedded=1'), 'id="knowledge-base"')
        for section in ('users', 'agents'):
            self.assertRedirects(self.client.get('/admin_' + section + '.html'),
                                 '/admin_panel.html#' + section, fetch_redirect_response=False)
            embedded = self.client.get('/admin_' + section + '.html?embedded=1')
            self.assertNotContains(embedded, 'aria-label="平台运营导航"')
            self.assertNotContains(embedded, 'id="btn-admin-logout"')
