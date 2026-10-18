"""Unified login routing and platform isolation, using isolated test data only."""
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from dadashop.utils import jwt_encode, md5
from users.models import Permission, Role, RolePermission, UserProfile, UserRole


class UnifiedLoginTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command('seed_rbac', verbosity=0)
        cls.merchant = cls.make_user('merchant001', 'merchant', 'supplier')
        cls.buyer = cls.make_user('buyer001', 'customer', 'buyer')
        cls.admin = cls.make_user('operator001', 'customer', 'super_admin')

    @staticmethod
    def make_user(username, user_type, role=None):
        user = UserProfile.objects.create(
            username=username, user_type=user_type, password=md5('test-only-123'),
            email=username + '@example.test', phone='', is_active=True,
        )
        if role:
            UserRole.objects.create(user_profile=user, role=Role.objects.get(code=role))
        return user

    def headers(self, user):
        token = jwt_encode({'id': user.pk, 'username': user.username})
        if isinstance(token, bytes):
            token = token.decode()
        return {'HTTP_AUTHORIZATION': 'Bearer ' + token}

    def login(self, user, **extra):
        # The cart store is irrelevant to permission routing; never connect to Redis.
        with patch('users.views.get_redis_connection') as redis:
            redis.return_value.get.return_value = None
            return self.client.post('/v1/users/login', {
                'username': user.username, 'password': 'test-only-123', **extra,
            }, content_type='application/json').json()

    def test_one_login_form_and_legacy_redirect(self):
        page = self.client.get('/login.html')
        self.assertContains(page, 'id="login-form"', count=1)
        self.assertNotContains(page, 'data-role=')
        self.assertNotContains(page, 'login-form-admin')
        self.assertRedirects(self.client.get('/terminal_login.html'), '/login.html')

    def test_destination_comes_from_account_not_client_role(self):
        for user, destination in (
            (self.merchant, '/merchant_dashboard.html'),
            (self.buyer, '/buyer_dashboard.html'),
            (self.admin, '/admin_panel.html'),
        ):
            with self.subTest(username=user.username):
                result = self.login(user, selectedRole='admin', redirect_url='/admin_panel.html')
                self.assertEqual(result['code'], 200)
                self.assertEqual(result['redirect_url'], destination)
                self.assertIn('token', result)
        result = self.login(self.merchant)
        self.assertEqual(result['roles'], ['supplier'])
        self.assertNotIn('user_manage', result['permissions'])

    def test_merchant_without_role_still_uses_merchant_workspace(self):
        UserRole.objects.filter(user_profile=self.merchant).delete()
        self.assertEqual(self.login(self.merchant)['redirect_url'], '/merchant_dashboard.html')

    def test_supplier_role_on_customer_account_uses_merchant_workspace(self):
        self.merchant.user_type = 'customer'
        self.merchant.save(update_fields=['user_type'])
        self.assertEqual(self.login(self.merchant)['redirect_url'], '/merchant_dashboard.html')

    def test_platform_role_requires_an_available_permission(self):
        operator = self.make_user('operator002', 'customer', 'admin')
        RolePermission.objects.filter(role__code='admin').delete()
        result = self.login(operator)
        self.assertEqual(result['code'], 10006)
        self.assertNotIn('token', result)
        RolePermission.objects.create(role=Role.objects.get(code='admin'),
                                      permission=Permission.objects.get(code='user_manage'))
        self.assertEqual(self.login(operator)['redirect_url'], '/admin_users.html')

    def test_system_config_only_operator_goes_to_agent_workspace(self):
        RolePermission.objects.filter(role__code='super_admin').exclude(
            permission__code='system_config').delete()
        self.assertEqual(self.login(self.admin)['redirect_url'], '/admin_agents.html')
        self.assertEqual(self.client.get('/v1/admin-panel/users', **self.headers(self.admin)).status_code, 403)
        self.assertEqual(self.client.get('/v1/admin-panel/agent/settings', **self.headers(self.admin)).status_code, 200)

    def test_data_only_operator_goes_to_overview_without_account_access(self):
        RolePermission.objects.filter(role__code='super_admin').exclude(
            permission__code='data_view').delete()
        self.assertEqual(self.login(self.admin)['redirect_url'], '/admin_panel.html')
        self.assertEqual(self.client.get('/v1/admin-panel/overview', **self.headers(self.admin)).status_code, 200)
        self.assertEqual(self.client.get('/v1/admin-panel/users', **self.headers(self.admin)).status_code, 403)

    def test_inactive_account_and_bad_password_do_not_issue_token(self):
        for extra in ({'password': 'incorrect'},):
            self.assertNotIn('token', self.login(self.merchant, **extra))
        self.merchant.is_active = False
        self.merchant.save(update_fields=['is_active'])
        self.assertEqual(self.login(self.merchant)['code'], 10004)

    def test_disabled_platform_role_or_permission_is_ignored(self):
        role = Role.objects.get(code='super_admin')
        role.is_active = False
        role.save(update_fields=['is_active'])
        self.assertEqual(self.login(self.admin)['redirect_url'], '/buyer_dashboard.html')
        self.assertEqual(self.client.get('/v1/admin-panel/users', **self.headers(self.admin)).status_code, 403)
        role.is_active = True
        role.save(update_fields=['is_active'])
        Permission.objects.filter(code='user_manage').update(is_active=False)
        self.assertEqual(self.login(self.admin)['redirect_url'], '/admin_panel.html')
        Permission.objects.filter(code='data_view').update(is_active=False)
        self.assertEqual(self.login(self.admin)['redirect_url'], '/admin_agents.html')

    def test_supplier_cannot_use_account_crud_even_with_forged_grants(self):
        # A wrongly assigned shared permission must not replace the platform role.
        RolePermission.objects.create(role=Role.objects.get(code='supplier'),
                                      permission=Permission.objects.get(code='user_manage'))
        count = UserProfile.objects.count()
        for method in ('get', 'post', 'put', 'delete'):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    '/v1/admin-panel/users', **self.headers(self.merchant))
                self.assertEqual(response.status_code, 403)
        self.assertEqual(UserProfile.objects.count(), count)

    def test_supplier_cannot_use_any_agent_endpoint_even_with_grant(self):
        RolePermission.objects.create(role=Role.objects.get(code='supplier'),
                                      permission=Permission.objects.get(code='system_config'))
        for path in ('settings', 'models', 'retrieval-status', 'monitoring', 'traces/example'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get('/v1/admin-panel/agent/' + path,
                                                **self.headers(self.merchant)).status_code, 403)
        self.assertEqual(self.client.put('/v1/admin-panel/agent/settings', '{}',
                                        content_type='application/json', **self.headers(self.merchant)).status_code, 403)

    def test_platform_permission_is_checked_on_every_request(self):
        headers = self.headers(self.admin)
        self.assertEqual(self.client.get('/v1/admin-panel/users', **headers).json()['code'], 200)
        RolePermission.objects.filter(role__code='super_admin', permission__code='user_manage').delete()
        self.assertEqual(self.client.get('/v1/admin-panel/users', **headers).status_code, 403)
        self.admin.is_active = False
        self.admin.save(update_fields=['is_active'])
        self.assertEqual(self.client.get('/v1/admin-panel/agent/settings', **headers).status_code, 403)
        self.assertEqual(self.client.get('/v1/users/session', **headers).status_code, 403)

    def test_session_requires_auth_and_returns_current_grants(self):
        self.assertEqual(self.client.get('/v1/users/session').status_code, 401)
        result = self.client.get('/v1/users/session', **self.headers(self.merchant)).json()
        self.assertEqual(result['redirect_url'], '/merchant_dashboard.html')
        self.assertEqual(result['roles'], ['supplier'])
        self.assertNotIn('password', result)
        self.assertEqual(self.client.post('/v1/users/session', **self.headers(self.admin)).status_code, 405)

    def test_authorized_operator_can_manage_an_account(self):
        headers = self.headers(self.admin)
        response = self.client.post('/v1/admin-panel/users', {
            'username': 'newbuyer', 'password': 'testing123', 'user_type': 'customer',
        }, content_type='application/json', **headers)
        self.assertEqual(response.json()['code'], 200)
        uid = response.json()['data']['id']
        response = self.client.put('/v1/admin-panel/users', {
            'id': uid, 'email': 'changed@example.test',
        }, content_type='application/json', **headers)
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(UserProfile.objects.get(pk=uid).email, 'changed@example.test')
        self.assertEqual(self.client.delete('/v1/admin-panel/users?id=' + str(uid), **headers).json()['code'], 200)
        self.assertFalse(UserProfile.objects.filter(pk=uid).exists())
