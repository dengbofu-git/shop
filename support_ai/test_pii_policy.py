"""Synthetic positive/negative samples; no external models or business data."""
from unittest import TestCase
from support_ai.pii import redact, contains_pii

SENSITIVE=['alice@example.com','13800138000','卡号4111 1111 1111 1111',
    '张三喜欢红茶','姓名：李四','地址：北京市朝阳区测试路88号',
    'IP 192.168.10.20','MAC aa:bb:cc:dd:ee:ff','账号 buyer_private',
    '证件110101199001011234','订单号：SYNTHETIC-123456']
PUBLIC=['推荐编号12345678的商品','商品编号12345678','SKU 12345678',
    '预算10000000元','价格 CNY 12345678.90','2026-11-02 每盒28.11元，买2盒',
    '绿茶喜欢低温冲泡吗','黄茶喜欢低温冲泡吗','陈皮喜欢热水冲泡吗','联系人工客服','ORDER_REF_abcdefgh_1',
    'https://example.com/public/tea.pdf']

class PiiPolicyTests(TestCase):
    def test_positive_samples_are_detected_and_idempotent(self):
        for text in SENSITIVE:
            with self.subTest(text=text):
                self.assertTrue(contains_pii(text))
                self.assertNotEqual(redact(text),text)
                self.assertEqual(redact(redact(text)),redact(text))

    def test_business_values_and_anonymous_references_survive(self):
        for text in PUBLIC:
            with self.subTest(text=text):self.assertEqual(redact(text),text)

    def test_product_context_does_not_allow_phone_card_or_identity(self):
        for text in ['商品编号13800138000','商品编号4111111111111111','商品编号110101199001011234']:
            with self.subTest(text=text):self.assertNotEqual(redact(text),text)

    def test_explicit_order_ids_are_always_removed(self):
        self.assertNotIn('PRIVATE-ORDER',redact('查询PRIVATE-ORDER',order_ids=['PRIVATE-ORDER']))

    def test_order_reference_randomness_consistency_and_forgery_protection(self):
        from support_ai.order_contracts import prepare_order_input
        text='订单号：PRIVATE-123456，订单号：PRIVATE-123456'
        safe, mapping=prepare_order_input(text)
        again, other=prepare_order_input(text)
        self.assertEqual(len(mapping),1)
        self.assertNotEqual(next(iter(mapping)),next(iter(other)))
        self.assertEqual(safe.count(next(iter(mapping))),2)
        self.assertNotIn('PRIVATE-123456',safe)
        forged, values=prepare_order_input('查询 ORDER_REF_abcdefgh_1')
        self.assertNotIn('ORDER_REF_abcdefgh_1',forged)
        self.assertEqual(values,{})

    def test_http_errors_and_nested_evidence_are_projected_before_return(self):
        from support_ai.views import _response
        raw=_response({'error':'alice@example.com','evidence':[{'text':'张三喜欢红茶'}]},400).content.decode()
        self.assertNotIn('alice@example.com',raw)
        self.assertNotIn('张三',raw)

    def test_labeled_name_does_not_consume_the_preference_verb(self):
        self.assertEqual(redact('我叫张三喜欢红茶'),'[姓名]喜欢红茶')

    def test_provider_boundary_scrubs_every_message_and_returned_text(self):
        from types import SimpleNamespace
        from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage
        from support_ai.model_client import AgentModel
        captured=[]
        client=SimpleNamespace(max_tokens=None,extra_body={},
            invoke=lambda prompt,**kw:(captured.append(prompt) or AIMessage(content='alice@example.com')))
        client.model_copy=lambda **kw:client
        result=AgentModel(client,'disabled').invoke([SystemMessage(content='历史alice@example.com'),
            AIMessage(content='张三喜欢红茶'),HumanMessage(content='13800138000'),
            ToolMessage(content='联系人邮箱alice@example.com',tool_call_id='safe-tool')])
        self.assertNotIn('alice@example.com',str(captured))
        self.assertNotIn('13800138000',str(captured))
        self.assertNotIn('张三',str(captured))
        self.assertNotIn('alice@example.com',result.content)

    def test_structured_model_output_and_knowledge_fragments_use_same_policy(self):
        from types import SimpleNamespace
        from pydantic import BaseModel
        from langchain_core.runnables import RunnableLambda
        from support_ai.model_client import AgentModel
        from support_ai.grounding import prepare_evidence
        class Answer(BaseModel):text:str
        client=SimpleNamespace(max_tokens=None,extra_body={})
        client.model_copy=lambda **kw:client
        client.with_structured_output=lambda *a,**kw:RunnableLambda(lambda prompt:{
            'parsed':Answer(text='alice@example.com'),'raw':None})
        result=AgentModel(client,'disabled').with_structured_output(Answer).invoke('合成问题')
        self.assertNotIn('alice@example.com',result.text)
        evidence=prepare_evidence([{'text':'联系人邮箱alice@example.com，张三喜欢红茶。'}])
        self.assertNotIn('alice@example.com',str(evidence))
        self.assertNotIn('张三',str(evidence))

    def test_sse_frames_filter_nested_terminal_errors_before_encoding(self):
        from support_ai.streaming import frame
        raw=frame('error',{'error':'请联系alice@example.com','detail':['13800138000'],'status':503}).decode()
        self.assertNotIn('alice@example.com',raw)
        self.assertNotIn('13800138000',raw)
        self.assertIn('503',raw)

    def test_sse_keeps_valid_protocol_uuids_but_does_not_whitelist_arbitrary_field_text(self):
        import json
        from support_ai.streaming import frame
        identity='12345678-1234-4234-8234-123456789012'
        data={'conversation_id':identity,'request_id':identity,'answer':'alice@example.com'}
        wire=frame('done',data).decode()
        self.assertIn(identity,wire)
        self.assertNotIn('alice@example.com',wire)
        self.assertNotIn('alice@example.com',frame('error',{'request_id':'alice@example.com'}).decode())


from django.test import TestCase as DatabaseTestCase

class PiiPersistenceTests(DatabaseTestCase):
    def test_new_turn_and_historical_read_projection_do_not_rewrite_old_rows(self):
        import uuid
        from users.models import UserProfile
        from support_ai.context import commit_turn
        from support_ai.models import SupportTurn
        from support_ai.conversation_history import history_value
        user=UserProfile.objects.create(username='synthetic-pii',is_active=True)
        result=commit_turn(user,None,0,uuid.uuid4(),'test-hash','张三喜欢红茶',
            {'answer':'alice@example.com','intent':'knowledge','nested':{'value':'13800138000'}})
        turn=SupportTurn.objects.get(user=user)
        self.assertNotIn('张三',turn.user_text)
        self.assertNotIn('alice@example.com',str(result))
        self.assertNotIn('13800138000',str(turn.response))
        SupportTurn.objects.filter(pk=turn.pk).update(answer='alice@example.com',response={'answer':'alice@example.com'})
        turn.refresh_from_db()
        self.assertNotIn('alice@example.com',str(history_value(turn.response)))
        turn.refresh_from_db()
        self.assertEqual(turn.answer,'alice@example.com')
