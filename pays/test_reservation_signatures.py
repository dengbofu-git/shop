import base64
from decimal import Decimal
from unittest.mock import patch
from Cryptodome.PublicKey import RSA
from Cryptodome.Signature import pkcs1_15
from Cryptodome.Hash import SHA256
from alipay import AliPay
from django.test import TestCase,override_settings
from orders.test_reservations import Fixtures
from orders.models import OrderInfo


@override_settings(ALIPAY_APP_ID='synthetic-app',ALIPAY_SELLER_ID='synthetic-seller')
class ProviderSignatureTests(Fixtures,TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.provider_key=RSA.generate(2048)
        cls.sdk=AliPay(appid='synthetic-app',app_notify_url=None,app_private_key_string=RSA.generate(2048).export_key().decode(),
                      alipay_public_key_string=cls.provider_key.public_key().export_key().decode())
    def setUp(self):self.seed()
    def payload(self,order):
        data={'app_id':'synthetic-app','seller_id':'synthetic-seller','trade_no':'local-signature-test','out_trade_no':order.pk,'total_amount':str(order.total_amount),'trade_status':'TRADE_SUCCESS'}
        message='&'.join('%s=%s'%item for item in sorted(data.items()))
        signature=base64.b64encode(pkcs1_15.new(self.provider_key).sign(SHA256.new(message.encode()))).decode()
        return {**data,'sign_type':'RSA2','sign':signature}
    def test_real_sdk_accepts_a_locally_signed_provider_notification(self):
        order=self.place()[0]
        with patch('pays.service.client',return_value=self.sdk):
            self.assertEqual(self.client.post('/v1/pays/notify',self.payload(order)).content,b'success')
        order.refresh_from_db();self.assertEqual(order.status,2)
    def test_changing_a_signed_amount_is_rejected_before_order_transition(self):
        order=self.place()[0];payload=self.payload(order);payload['total_amount']='0.01'
        with patch('pays.service.client',return_value=self.sdk):
            self.assertEqual(self.client.post('/v1/pays/notify',payload).status_code,400)
        order.refresh_from_db();self.assertEqual(order.status,1)
