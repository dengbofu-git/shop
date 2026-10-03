from unittest import TestCase
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda

from .pii import contains_pii, redact
from .workflow import ComplianceVerdict, FALLBACK, IntentScores, build_graph, configured_model


class FakeModel(Runnable):
    def __init__(self, scores):
        self.scores = scores
        self.calls = []

    def with_structured_output(self, schema):
        def structured(prompt):
            content = prompt.to_messages()[-1].content
            self.calls.append(('structured', content))
            if schema is IntentScores:
                return IntentScores(**self.scores)
            return ComplianceVerdict(safe=True, revised_answer=content.split('待检查回复：')[-1])
        return RunnableLambda(structured)

    def invoke(self, input, config=None, **kwargs):
        system = input.to_messages()[0].content
        self.calls.append(('text', system))
        if '总结 Agent' in system:
            return AIMessage(content=input.to_messages()[-1].content.split('专家草稿：')[-1])
        return AIMessage(content='已根据授权资料回答。')


class PiiTests(TestCase):
    def test_redacts_order_phone_email_name_and_address(self):
        result = redact('姓名：张三 电话13800138000 邮箱a@b.com 地址：北京市朝阳区某路9号 订单20260901000001', ['20260901000001'])
        for secret in ('张三', '13800138000', 'a@b.com', '北京市', '20260901000001'):
            self.assertNotIn(secret, result)
        self.assertTrue(contains_pii('test@example.com'))


class GraphTests(TestCase):
    def test_low_confidence_uses_fallback_then_compliance(self):
        model = FakeModel({'recommendation': .2, 'question_answering': .3, 'after_sales': .1})
        result = build_graph(model).invoke({'message': '无关问题'})
        self.assertEqual(result['intent'], 'unavailable')
        self.assertEqual(result['answer'], FALLBACK)
        self.assertEqual(len([call for call in model.calls if call[0] == 'structured']), 2)

    def test_pii_node_runs_before_classifier(self):
        model = FakeModel({'recommendation': .1, 'question_answering': .8, 'after_sales': .1})
        result = build_graph(model).invoke({'message': '我的邮箱是 private@example.com，如何查看订单？'})
        self.assertTrue(result['pii_redacted'])
        for _, content in model.calls:
            self.assertNotIn('private@example.com', content)

    def test_order_context_is_loaded_only_for_after_sales(self):
        calls = []
        provider = lambda: calls.append('used') or '[]'
        qa = FakeModel({'recommendation': .1, 'question_answering': .9, 'after_sales': .1})
        build_graph(qa, provider).invoke({'message': '如何查看订单？'})
        self.assertEqual(calls, [])
        after_sales = FakeModel({'recommendation': .1, 'question_answering': .1, 'after_sales': .9})
        build_graph(after_sales, provider).invoke({'message': '订单售后问题'})
        self.assertEqual(calls, ['used'])

    def test_each_specialist_reaches_summary_and_compliance(self):
        for intent in ('recommendation', 'question_answering', 'after_sales'):
            with self.subTest(intent=intent):
                scores = dict.fromkeys(('recommendation', 'question_answering', 'after_sales'), .1)
                scores[intent] = .9
                model = FakeModel(scores)
                if intent == 'recommendation':
                    context = patch('support_ai.workflow._catalog_context', return_value='[]')
                else:
                    from contextlib import nullcontext
                    context = nullcontext()
                with context:
                    result = build_graph(model).invoke({'message': '请帮忙'})
                self.assertEqual(result['intent'], intent)
                self.assertIn('已根据授权资料回答', result['answer'])
                self.assertEqual(len([call for call in model.calls if call[0] == 'text']), 2)
                self.assertEqual(len([call for call in model.calls if call[0] == 'structured']), 2)


@override_settings(ALLOWED_HOSTS=['127.0.0.1', 'testserver'])
class BuyerShellTests(SimpleTestCase):
    def test_buyer_pages_share_header_and_support_navigation(self):
        pages = ('buyer_dashboard.html', 'buyer_products.html', 'cart.html', 'buyer_orders.html', 'buyer_support.html')
        headers = []
        for page in pages:
            response = self.client.get('/' + page, HTTP_HOST='127.0.0.1')
            self.assertEqual(response.status_code, 200)
            html = response.content.decode('utf-8')
            self.assertIn('href="buyer_support.html"', html)
            self.assertEqual(html.count('aria-current="page"'), 1)
            headers.append(html.split('<header class="buyer-topbar"', 1)[1].split('</header>', 1)[0])
        self.assertEqual(len(set(headers)), 1)

    def test_support_requires_login(self):
        response = self.client.post('/v1/support/chat/', data='{}', content_type='application/json', HTTP_HOST='127.0.0.1')
        self.assertEqual(response.status_code, 401)


class ModelConfigurationTests(SimpleTestCase):
    def test_model_uses_configured_deepseek_options(self):
        with patch('support_ai.workflow.ChatOpenAI') as chat_model:
            configured_model()
        options = chat_model.call_args.kwargs
        self.assertEqual(options['model'], settings.SUPPORT_MODEL)
        self.assertEqual(options['base_url'], settings.SUPPORT_BASE_URL)
        self.assertEqual(options['extra_body']['thinking']['type'], settings.SUPPORT_THINKING)
        self.assertTrue(options['api_key'])
