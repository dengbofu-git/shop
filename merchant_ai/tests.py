"""Entry/authentication contract checks; no business database or external model."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from django.urls import resolve


class MerchantAssistantEntryTests(SimpleTestCase):
    def status_as(self, merchant=False, supplier=False, active=True):
        user = SimpleNamespace(
            is_active=active,
            is_merchant=lambda: merchant,
            has_role=lambda role: supplier and role == 'supplier',
        )
        with patch('users.decorators.jwt_decode', return_value={'id': 7}), \
                patch('users.decorators.UserProfile.objects.get', return_value=user):
            return self.client.get('/v1/merchant-ai/status/', HTTP_AUTHORIZATION='Bearer test-token')

    def test_active_merchant_sees_empty_capabilities_and_no_cache(self):
        response = self.status_as(merchant=True)
        self.assertEqual(response.status_code, 200)
        data = response.json()['data']
        self.assertEqual(data['module'], 'merchant_ai')
        self.assertEqual(data['version'], '0.1.0')
        self.assertEqual(data['status'], 'initialized')
        self.assertFalse(data['chat_enabled'])
        self.assertFalse(data['model_connected'])
        self.assertEqual(data['capabilities'], [])
        self.assertIn('no-store', response['Cache-Control'])

    def test_supplier_role_can_access(self):
        self.assertEqual(self.status_as(supplier=True).status_code, 200)

    def test_customer_is_denied(self):
        self.assertEqual(self.status_as().status_code, 403)

    def test_inactive_merchant_is_denied(self):
        self.assertEqual(self.status_as(merchant=True, active=False).status_code, 403)

    def test_missing_token_is_denied(self):
        self.assertEqual(self.client.get('/v1/merchant-ai/status/').status_code, 401)

    def test_invalid_token_is_denied(self):
        with patch('users.decorators.jwt_decode', side_effect=ValueError('invalid token')):
            response = self.client.get('/v1/merchant-ai/status/', HTTP_AUTHORIZATION='Bearer bad-token')
        self.assertEqual(response.status_code, 401)

    def test_status_does_not_accept_writes(self):
        response = self.client.post('/v1/merchant-ai/status/', {'message': '测试'})
        self.assertEqual(response.status_code, 405)

    def test_page_keeps_composer_disabled_and_has_no_upload(self):
        response = self.client.get('/merchant_assistant.html?embed=1')
        self.assertContains(response, '商家智能助手')
        self.assertContains(response, 'id="ma-input" rows="2" disabled')
        self.assertContains(response, 'id="ma-send" type="button" disabled')
        self.assertNotContains(response, 'type="file"')
        self.assertNotContains(response, 'buyer-support.js')

    def test_workbench_contains_panel_entry(self):
        response = self.client.get('/merchant_dashboard.html')
        self.assertContains(response, 'data-panel="merchant_assistant.html"')

    def test_no_chat_or_upload_endpoint(self):
        self.assertEqual(resolve('/v1/merchant-ai/status/').view_name, 'merchant_ai:status')
        self.assertEqual(self.client.post('/v1/merchant-ai/chat/', {}).status_code, 404)
        self.assertEqual(self.client.post('/v1/merchant-ai/uploads/', {}).status_code, 404)
