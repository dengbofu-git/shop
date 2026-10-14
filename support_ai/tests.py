from unittest import TestCase
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.test import TestCase as DatabaseTestCase
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda

from .pii import contains_pii, redact
from .workflow import ComplianceVerdict, FALLBACK, IntentScores, build_graph
from .model_client import configured_model
from .contracts import RecommendationIntent, validate_recommendation_intent


class FakeModel(Runnable):
    def __init__(self, scores, product_intent=None):
        self.scores = scores
        self.calls = []
        self.product_intent = product_intent or {'action': 'SEARCH'}

    def with_structured_output(self, schema):
        def structured(prompt):
            content = prompt.to_messages()[-1].content
            self.calls.append(('structured', content))
            if schema is IntentScores:
                return IntentScores(**self.scores)
            if schema is RecommendationIntent:
                return RecommendationIntent.model_validate(self.product_intent)
            return ComplianceVerdict(safe=True, revised_answer=content.split('待检查回复：')[-1])
        return RunnableLambda(structured)

    def invoke(self, input, config=None, **kwargs):
        system = input.to_messages()[0].content
        self.calls.append(('text', system + '\n' + input.to_messages()[-1].content))
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
        context = '[{"status":"待付款"}]'
        qa = FakeModel({'recommendation': .1, 'question_answering': .9, 'after_sales': .1})
        build_graph(qa).invoke({'message': '如何查看订单？', 'order_context': context})
        self.assertFalse(any(context in text for _, text in qa.calls))
        after_sales = FakeModel({'recommendation': .1, 'question_answering': .1, 'after_sales': .9})
        build_graph(after_sales).invoke({'message': '订单售后问题', 'order_context': context})
        self.assertTrue(any(context in text for _, text in after_sales.calls))

    def test_each_specialist_reaches_summary_and_compliance(self):
        for intent in ('question_answering', 'after_sales'):
            with self.subTest(intent=intent):
                scores = dict.fromkeys(('recommendation', 'question_answering', 'after_sales'), .1)
                scores[intent] = .9
                model = FakeModel(scores)
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
            # Cart is a topbar action, not a sidebar destination.
            self.assertEqual(html.count('aria-current="page"'), 0 if page == 'cart.html' else 1)
            headers.append(html.split('<header class="buyer-topbar"', 1)[1].split('</header>', 1)[0])
        self.assertEqual(len(set(headers)), 1)

    def test_support_requires_login(self):
        response = self.client.post('/v1/support/chat/', data='{}', content_type='application/json', HTTP_HOST='127.0.0.1')
        self.assertEqual(response.status_code, 401)

    def test_support_page_contains_preference_controls_and_new_conversation(self):
        html = self.client.get('/buyer_support.html').content.decode('utf-8')
        for element in ('bs-preferences-form', 'bs-clear-preferences', 'bs-new-conversation'):
            self.assertIn('id="{}"'.format(element), html)


class ModelConfigurationTests(SimpleTestCase):
    def test_model_uses_configured_deepseek_options(self):
        with patch('support_ai.model_client.ChatOpenAI') as chat_model:
            configured_model()
        options = chat_model.call_args.kwargs
        self.assertEqual(options['model'], settings.SUPPORT_MODEL)
        self.assertEqual(options['base_url'], settings.SUPPORT_BASE_URL)
        if settings.SUPPORT_THINKING:
            self.assertEqual(options['extra_body']['thinking']['type'], settings.SUPPORT_THINKING)
        self.assertTrue(options['api_key'])


class RecommendationGraphTests(SimpleTestCase):
    def test_recommendation_graph_only_extracts_intent_without_database_or_text_models(self):
        memory = {'id': 'preference-1', 'preferences': {'categories': ['红茶'], 'brands': [], 'keywords': []}}
        history = [{'turn_id': 'turn-1', 'user_text': '想买红茶', 'assistant_text': '已找到商品'}]
        model = FakeModel({'recommendation': .9, 'question_answering': .1, 'after_sales': .1})
        result = build_graph(model).invoke({'message': '还是红茶', 'memory': memory, 'recent_turns': history})
        self.assertEqual(result['product_intent']['action'], 'SEARCH')
        self.assertNotIn('answer', result)
        self.assertEqual([kind for kind, _ in model.calls], ['structured', 'structured'])
        self.assertIn('preference-1', model.calls[-1][1])
        self.assertIn('turn-1', model.calls[-1][1])


def evidence(field, value, quote, source='CURRENT', source_id=None):
    return {'field': field, 'value': value, 'quote': quote, 'source': source, 'source_id': source_id}


class RecommendationContractTests(SimpleTestCase):
    def test_requires_original_user_evidence_and_rejects_injected_query_fields(self):
        for payload in (
            {'action': 'SEARCH', 'sql': 'SELECT * FROM goods_sku'},
            {'action': 'SEARCH', 'required': {'categories': ['绿茶']}},
            {'action': 'SEARCH', 'required': {'categories': ['绿茶']},
             'evidence': [evidence('required.categories', '绿茶', '绿茶', 'CONTEXT', 'another-user-turn')]},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validate_recommendation_intent(payload, '推荐红茶', [], None)

    def test_memory_cannot_supply_hard_conditions(self):
        memory = {'id': 'm1', 'preferences': {'categories': ['红茶']}}
        payload = {'action': 'SEARCH', 'required': {'categories': ['红茶']},
                   'evidence': [evidence('required.categories', '红茶', '红茶', 'MEMORY', 'm1')]}
        with self.assertRaises(ValueError):
            validate_recommendation_intent(payload, '推荐茶', [], memory)

    def test_current_category_overrides_long_term_preference(self):
        memory = {'id': 'm1', 'preferences': {'categories': ['红茶']}}
        payload = {'action': 'SEARCH', 'required': {'categories': ['绿茶']}, 'preferred': {'categories': ['红茶']},
                   'evidence': [evidence('required.categories', '绿茶', '绿茶'),
                                evidence('preferred.categories', '红茶', '红茶', 'MEMORY', 'm1')]}
        result = validate_recommendation_intent(payload, '这次要绿茶', [], memory)
        self.assertEqual(result.required.categories, ['绿茶'])
        self.assertEqual(result.preferred.categories, [])

    def test_unknown_currency_or_total_budget_clarifies_instead_of_becoming_unit_price(self):
        payload = {'action': 'SEARCH', 'required': {'price_max': '50', 'price_basis': 'total'},
                   'evidence': [evidence('required.price_max', '50', '总预算50'),
                                evidence('required.price_basis', 'total', '总预算50')]}
        result = validate_recommendation_intent(payload, '总预算50', [], None)
        self.assertEqual(result.action, 'CLARIFY')
        self.assertEqual(set(result.missing_fields), {'currency', 'budget_scope'})

    def test_only_known_recent_user_turns_can_supply_continuation(self):
        payload = {'action': 'SEARCH', 'required': {'categories': ['红茶']},
                   'evidence': [evidence('required.categories', '红茶', '红茶', 'CONTEXT', 't1')]}
        result = validate_recommendation_intent(payload, '还是刚才那类',
                                               [{'turn_id': 't1', 'user_text': '想买红茶'}], None)
        self.assertEqual(result.required.categories, ['红茶'])
        with self.assertRaises(ValueError):
            validate_recommendation_intent(payload, '还是刚才那类',
                                           [{'turn_id': 't1', 'user_text': '推荐茶', 'assistant_text': '红茶'}], None)


class RecommendationIntegrationTests(DatabaseTestCase):
    databases = {'default', 'ai_storage'}
    def setUp(self):
        import uuid
        from decimal import Decimal
        from dadashop.utils import jwt_encode
        from goods.models import Brand, Catalog, SKU, SPU
        from users.models import UserProfile
        self.user = UserProfile.objects.create(username='test-buyer', password='test', email='buyer@test.com', phone='', is_active=True)
        self.other = UserProfile.objects.create(username='other-buyer', password='test', email='other@test.com', phone='', is_active=True)
        self.auth = {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': self.user.pk})}
        self.request_id = str(uuid.uuid4())
        brand = Brand.objects.create(name='测试品牌', first_letter='T')
        red = Catalog.objects.create(name='红茶')
        green = Catalog.objects.create(name='绿茶')
        self.skus = []
        for name, category, price, stock, launched in (
            ('红茶优选', red, '20', 10, True), ('绿茶优选', green, '40', 10, True),
            ('绿茶高价', green, '100', 10, True), ('绿茶无货', green, '30', 0, True),
            ('绿茶下架', green, '30', 10, False), ('绿茶预留', green, '30', 10, True),
        ):
            spu = SPU.objects.create(name=name, catalog=category, brand=brand)
            self.skus.append(SKU.objects.create(name=name, caption='', spu=spu, price=Decimal(price),
                                                cost_price=Decimal(price), market_price=Decimal(price),
                                                stock=stock, is_launched=launched))
        from inventory.models import Inventory, Warehouse
        warehouse = Warehouse.objects.create(name='测试仓', code='SUPPORT-TEST', address='')
        Inventory.objects.create(sku=self.skus[-1], warehouse=warehouse, quantity=10, reserved_quantity=10)

    def post_chat(self, model, **kwargs):
        import json
        body = dict(message='推荐茶', request_id=self.request_id)
        body.update(kwargs)
        with patch('support_ai.model_client.configured_model', return_value=model):
            return self.client.post('/v1/support/chat/', data=json.dumps(body), content_type='application/json', **self.auth)

    def model(self, payload=None):
        return FakeModel({'recommendation': .9, 'question_answering': .1, 'after_sales': .1}, payload)

    def test_matching_enforces_budget_launch_and_inventory_without_popular_fallback(self):
        from .recommendations import match_products
        intent = RecommendationIntent(action='SEARCH', required={'categories': ['绿茶'], 'price_max': '50',
                                                                'currency': 'USD', 'price_basis': 'unit'})
        result = match_products(intent)
        self.assertEqual([card['sku_id'] for card in result['recommendations']], [self.skus[1].pk])
        self.assertEqual(result['recommendations'][0]['price'], '40.00')
        intent.required.price_max = '10.00'
        empty = match_products(intent)
        self.assertEqual(empty['recommendation_status'], 'NO_MATCH')
        self.assertEqual(empty['recommendations'], [])

    def test_http_recommendation_uses_saved_memory_and_commits_exact_replay(self):
        from .context import saved_preferences
        from .models import SupportTurn
        from ai_storage.models import BuyerMemory
        BuyerMemory.objects.create(owner_id=self.user.pk, preferences={'categories': ['红茶'], 'brands': [], 'keywords': []})
        memory = saved_preferences(self.user)
        model = self.model({'action': 'SEARCH', 'preferred': {'categories': ['红茶']},
                            'evidence': [evidence('preferred.categories', '红茶', '红茶', 'MEMORY', memory['id'])]})
        first = self.post_chat(model)
        self.assertEqual(first.status_code, 200)
        data = first.json()
        self.assertEqual(data['recommendations'][0]['sku_id'], self.skus[0].pk)
        self.assertTrue(data['memory_used'])
        self.assertEqual(data['revision'], 1)
        self.assertEqual(len(model.calls), 2)
        with patch('support_ai.model_client.configured_model', side_effect=AssertionError('must replay')):
            import json
            second = self.client.post('/v1/support/chat/', data=json.dumps({'message': '推荐茶', 'request_id': self.request_id}),
                                      content_type='application/json', **self.auth)
        self.assertEqual(second.json(), data)
        self.assertEqual(SupportTurn.objects.filter(user=self.user).count(), 1)

    def test_other_users_conversations_and_preferences_are_isolated(self):
        from .models import SupportConversation
        from ai_storage.models import BuyerMemory
        foreign = SupportConversation.objects.create(user=self.other)
        BuyerMemory.objects.create(owner_id=self.other.pk, preferences={'categories': ['红茶']})
        result = self.post_chat(self.model(), conversation_id=str(foreign.pk))
        self.assertEqual(result.status_code, 404)
        self.assertEqual(self.client.get('/v1/support/conversations/{}/'.format(foreign.pk), **self.auth).status_code, 404)
        self.assertEqual(self.client.get('/v1/support/preferences/', **self.auth).json()['preferences']['categories'], [])

    def test_invalid_model_output_and_model_failure_do_not_commit_a_turn(self):
        from .models import SupportConversation, SupportTurn
        bad = self.model({'action': 'SEARCH', 'required': {'categories': ['绿茶']}})
        self.assertEqual(self.post_chat(bad).status_code, 503)
        self.assertFalse(SupportTurn.objects.filter(user=self.user).exists())
        self.assertFalse(SupportConversation.objects.filter(user=self.user).exists())
        with patch('support_ai.model_client.configured_model', side_effect=TimeoutError):
            import json
            response = self.client.post('/v1/support/chat/', data=json.dumps({'message': '推荐茶'}),
                                        content_type='application/json', **self.auth)
        self.assertEqual(response.status_code, 503)
        self.assertFalse(SupportTurn.objects.filter(user=self.user).exists())

    def test_retry_payload_conflict_and_conversation_revision_conflict(self):
        import json
        first = self.post_chat(self.model()).json()
        changed = self.client.post('/v1/support/chat/', data=json.dumps({'message': '不同问题', 'request_id': self.request_id}),
                                   content_type='application/json', **self.auth)
        self.assertEqual(changed.status_code, 409)
        import uuid
        self.request_id = str(uuid.uuid4())
        stale = self.post_chat(self.model(), conversation_id=first['conversation_id'], expected_revision=0)
        self.assertEqual(stale.status_code, 409)

    def test_preferences_are_explicit_validated_and_deletable(self):
        import json
        from ai_storage.models import BuyerMemory
        for values in ({'user_id': self.other.pk, 'categories': ['红茶']}, {'price_max': '50'},
                       {'keywords': ['my@email.com']}):
            response = self.client.put('/v1/support/preferences/', data=json.dumps(values), content_type='application/json', **self.auth)
            self.assertEqual(response.status_code, 400)
        response = self.client.put('/v1/support/preferences/', data=json.dumps({'categories': ['红茶']}),
                                   content_type='application/json', **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(BuyerMemory.objects.filter(owner_id=self.user.pk).exists())
        self.assertEqual(self.client.delete('/v1/support/preferences/', **self.auth).status_code, 200)
        self.assertFalse(BuyerMemory.objects.filter(owner_id=self.user.pk).exists())

    def test_short_context_contains_only_committed_redacted_same_conversation_turns(self):
        import uuid
        from .context import recent_context
        from .models import SupportConversation
        model = self.model()
        first = self.post_chat(model, message='推荐茶，邮箱buyer@example.com').json()
        context = recent_context(SupportConversation.objects.get(pk=first['conversation_id']))
        self.assertNotIn('buyer@example.com', context[0]['user_text'])
        self.request_id = str(uuid.uuid4())
        next_model = self.model()
        response = self.post_chat(next_model, conversation_id=first['conversation_id'], expected_revision=1)
        self.assertEqual(response.status_code, 200)
        self.assertIn('turn-', next_model.calls[-1][1])
        self.assertNotIn('buyer@example.com', next_model.calls[-1][1])

    def test_short_context_excludes_old_turns_and_unrelated_conversations(self):
        from datetime import timedelta
        from django.utils import timezone
        from .context import recent_context
        from .models import SupportConversation, SupportTurn
        first = self.post_chat(self.model()).json()
        own = SupportConversation.objects.get(pk=first['conversation_id'])
        other = SupportConversation.objects.create(user=self.user)
        self.assertEqual(recent_context(other), [])
        SupportTurn.objects.filter(conversation=own).update(created_at=timezone.now() - timedelta(hours=25))
        self.assertEqual(recent_context(own), [])

    def test_commit_rechecks_revision_after_slow_model_work(self):
        import uuid
        from .context import ConversationConflict, commit_turn
        from .models import SupportConversation, SupportTurn
        conversation = SupportConversation.objects.create(user=self.user)
        SupportConversation.objects.filter(pk=conversation.pk).update(revision=1)
        with self.assertRaises(ConversationConflict):
            commit_turn(self.user, conversation, 0, uuid.uuid4(), 'hash', '推荐茶',
                        {'answer': '候选回复', 'intent': 'recommendation'})
        self.assertFalse(SupportTurn.objects.filter(conversation=conversation).exists())

    def test_unavailable_memory_database_returns_safe_503_without_model_or_commit(self):
        from django.db import OperationalError
        from .models import SupportTurn
        model = self.model()
        with patch('support_ai.views.saved_preferences', side_effect=OperationalError('private connection information')):
            response = self.post_chat(model)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn('private connection', response.content.decode())
        self.assertEqual(model.calls, [])
        self.assertFalse(SupportTurn.objects.filter(user=self.user).exists())

    def test_unavailable_preference_store_does_not_fall_back_to_mysql(self):
        from django.db import OperationalError
        with patch('support_ai.views.saved_preferences', side_effect=OperationalError):
            response = self.client.get('/v1/support/preferences/', **self.auth)
        self.assertEqual(response.status_code, 503)
