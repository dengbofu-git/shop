"""Follow-up surfaces use synthetic data and the real application adapters."""
from unittest import TestCase
from types import SimpleNamespace
from langchain_core.messages import AIMessage
from .pii import redact_value

IDENTITY='12345678-1234-4234-8234-123456789012'

class PiiSurfaceTests(TestCase):
    def test_history_and_preview_share_uuid_safe_recursive_projection(self):
        from .conversation_history import history_value
        from .preview import safe_record
        payload={'conversation_id':IDENTITY,'request_id':IDENTITY,
            'notes':['alice@example.com'],'amount':28.11,'sku_id':12345678}
        for project in (history_value,safe_record):
            with self.subTest(project=project.__name__):
                safe=project(payload)
                self.assertEqual(safe,redact_value(payload))
                self.assertEqual(safe['conversation_id'],IDENTITY)
                self.assertEqual(safe['amount'],28.11)
                self.assertNotIn('alice@example.com',str(safe))
        self.assertEqual(payload['notes'],['alice@example.com'])

    def test_invalid_model_tool_calls_are_filtered_before_leaving_adapter(self):
        from .model_client import AgentModel
        message=AIMessage(content='',invalid_tool_calls=[{'name':'synthetic',
            'args':'{"email":"alice@example.com"','id':'call-safe','error':'13800138000'}])
        client=SimpleNamespace(max_tokens=None,extra_body={},invoke=lambda *a,**kw:message)
        client.model_copy=lambda **kw:client
        safe=AgentModel(client,'disabled').invoke('合成输入')
        self.assertNotIn('alice@example.com',str(safe.invalid_tool_calls))
        self.assertNotIn('13800138000',str(safe.invalid_tool_calls))

    def test_explicit_contact_fields_cannot_hide_pii_as_numbers_or_bare_names(self):
        payload={'receiver_mobile':13800138000,'receiver':'张三','email':'alice@example.com',
            'nested':{'sku_id':12345678,'count':2,'price':28.11},'phone':False}
        safe=redact_value(payload)
        self.assertNotIn('13800138000',str(safe))
        self.assertNotIn('张三',str(safe))
        self.assertEqual(safe['nested'],payload['nested'])
        self.assertIs(safe['phone'],False)
