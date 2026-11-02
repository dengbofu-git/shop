"""Opaque bundle references are public identity, never purchase authorization."""
import json
from unittest import TestCase
from langchain_core.messages import HumanMessage
from .pii import redact,redact_messages,redact_value

class BundleReferencePiiTests(TestCase):
    def test_bundle_hash_with_digits_survives_text_and_model_json(self):
        identity='bundle-12345678abcd'
        self.assertEqual(redact(identity),identity)
        payload={'bundle_id':identity,'primary_bundle_id':identity,'answer':'可查看方案'}
        self.assertEqual(redact_value(payload),payload)
        prompt=HumanMessage(content=json.dumps(payload,ensure_ascii=False))
        self.assertIn(identity,redact_messages([prompt])[0].content)

    def test_bundle_prefix_does_not_whitelist_a_phone_or_invalid_reference(self):
        for text in ('bundle-13800138000a','bundle-1234567890123456','bundle-12345678zzzz'):
            with self.subTest(text=text):self.assertNotEqual(redact(text),text)

    def test_reference_does_not_suppress_neighboring_pii(self):
        text='bundle-12345678abcd 联系alice@example.com 电话13800138000'
        safe=redact(text)
        self.assertIn('bundle-12345678abcd',safe)
        self.assertNotIn('alice@example.com',safe)
        self.assertNotIn('13800138000',safe)
