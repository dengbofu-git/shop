import json
import uuid
from unittest.mock import patch

from django.test import TestCase
from langchain_core.messages import AIMessage
from langchain_core.runnables import Runnable, RunnableLambda

from .contracts import RecommendationIntent
from .planning import FiniteIntents
from .workflow import ComplianceVerdict, DialogueResolution
from .semantic_planning import SemanticPlan


class ToolModel(Runnable):
    def __init__(self, payload=None):
        self.payload = payload or {'action': 'SEARCH'}

    def with_structured_output(self, schema):
        def structured(prompt):
            text = prompt.to_messages()[-1].content
            if schema is SemanticPlan:
                message = text.split('本轮原话：')[1].split('\n')[0]
                if message == '先介绍绿茶，再推荐一款绿茶':
                    requests = [{'kind': 'question_answering', 'quote': '先介绍绿茶'},
                                {'kind': 'recommendation', 'quote': '再推荐一款绿茶', 'limit': 1}]
                else:
                    requests = [{'kind': 'recommendation', 'quote': message}]
                return SemanticPlan(action='new_request', standalone_question=message,
                                    requests=requests, purchase=self.payload)
            if schema is RecommendationIntent:
                return RecommendationIntent.model_validate(self.payload)
            if schema is DialogueResolution:
                return DialogueResolution(standalone_question=text.split('本轮：')[1].split('\n')[0],
                                          source_turn_ids=[], needs_clarification=False)
            if schema is FiniteIntents:
                return FiniteIntents(requests=[{'kind': 'clarification', 'quote': '不明确'}])
            return ComplianceVerdict(safe=True, revised_answer=text.split('待检查回复：')[-1])
        return RunnableLambda(structured)

    def invoke(self, input, config=None, **kwargs):
        return AIMessage(content='已根据本次工具证据介绍茶叶，并列出匹配商品。')


class TaskToolIntegrationTests(TestCase):
    databases = {'default', 'ai_storage'}

    def setUp(self):
        from users.models import UserProfile
        from goods.models import Catalog, SPU, SKU
        from tea_saas.utils import jwt_encode
        self.user = UserProfile.objects.create(username='plan-buyer', password='unused', email='planner@test.invalid', phone='', is_active=True)
        self.auth = {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': self.user.pk})}
        category = Catalog.objects.create(name='绿茶')
        spu = SPU.objects.create(name='可验证绿茶', catalog=category)
        self.skus = [SKU.objects.create(name='规格' + str(i), caption='', spu=spu, price='50',
                                       cost_price='40', market_price='60', stock=10) for i in range(2)]

    def chat(self, message, payload=None, **extra):
        data = dict(message=message, request_id=str(uuid.uuid4()), **extra)
        evidence = [{'chunk_id': 1, 'source_title': '测试茶类资料', 'source_reference': 'https://example.invalid/tea',
                     'metadata': {'year': 2026}, 'text': '绿茶以加热钝化酶，随后干燥。'}]
        with patch('support_ai.model_client.configured_model', return_value=ToolModel(payload)), \
                patch('support_ai.retrieval.retrieve_knowledge', return_value=evidence):
            return self.client.post('/v1/support/chat/', data=json.dumps(data), content_type='application/json', **self.auth)

    def test_generic_category_is_range_not_false_no_match(self):
        response = self.chat('推荐茶叶', {'action': 'SEARCH', 'required': {'categories': ['茶叶']},
                             'evidence': [{'field': 'required.categories', 'value': '茶叶', 'quote': '推荐茶叶', 'source': 'CURRENT'}]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['recommendations']), 2)
        self.assertEqual(response.json()['product_intent']['required']['categories'], [])

    def test_one_product_and_dependent_live_details(self):
        response = self.chat('推荐一款绿茶，再介绍这款商品的特点')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['intents'], ['recommendation', 'product_details'])
        self.assertEqual(len(data['recommendations']), 1)
        self.assertEqual([t['status'] for t in data['tasks']], ['success', 'success'])
        self.assertEqual(data['task_plan']['steps'][1]['depends_on'], ['s1'])

    def test_knowledge_and_recommendation_both_execute_in_user_order(self):
        data = self.chat('先介绍绿茶，再推荐一款绿茶').json()
        self.assertEqual(data['intents'], ['question_answering', 'recommendation'])
        self.assertEqual([t['tool'] for t in data['tasks']], ['introduce_tea', 'recommend_products'])
        self.assertEqual(len(data['recommendations']), 1)
        self.assertTrue(data['knowledge_sources'])

    def test_invalid_hard_conditions_commit_only_safe_clarification(self):
        from .models import SupportTurn
        with patch('support_ai.tool_services.match_products') as query:
            response = self.chat('推荐测试品牌绿茶', {'action': 'SEARCH', 'required': {'categories': ['绿茶']}})
        query.assert_not_called()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['clarification_required'])
        self.assertEqual([(t['tool'], t['status']) for t in response.json()['tasks']],
                         [('ask_clarification', 'needs_clarification')])
        self.assertFalse(response.json()['recommendations'])
        self.assertEqual(SupportTurn.objects.count(), 1)

    def test_saved_preference_quote_is_canonicalized_only_after_owner_verification(self):
        from ai_storage.models import BuyerMemory
        from .context import saved_preferences
        BuyerMemory.objects.create(owner_id=self.user.pk, preferences={'categories': ['绿茶'], 'brands': [], 'keywords': []})
        memory = saved_preferences(self.user)
        payload = {'action': 'SEARCH', 'preferred': {'categories': ['绿茶']}, 'evidence': [
            {'field': 'preferred.categories', 'value': '绿茶', 'quote': 'categories: 绿茶', 'source': 'MEMORY', 'source_id': memory['id']}]}
        question = '请按已保存的偏好推荐一款商品'
        data = self.chat(question, payload).json()
        self.assertTrue(data['memory_used'])
        self.assertEqual(data['product_intent']['evidence'][0]['quote'], '绿茶')
        payload['evidence'][0]['source_id'] = 'another-owner-preference'
        rejected = self.chat(question, payload).json()
        self.assertTrue(rejected['clarification_required'])
        self.assertFalse(rejected['recommendations'])
        self.assertEqual([t['tool'] for t in rejected['tasks']], ['ask_clarification'])

    def test_unknown_category_requests_clarification_instead_of_no_match(self):
        data = self.chat('推荐岩茶', {'action': 'SEARCH', 'required': {'categories': ['岩茶']},
                         'evidence': [{'field': 'required.categories', 'value': '岩茶', 'quote': '推荐岩茶', 'source': 'CURRENT'}]}).json()
        self.assertEqual(data['recommendation_status'], 'CLARIFY')
        self.assertEqual(data['tasks'][0]['status'], 'needs_clarification')

    def test_exact_preference_request_uses_authenticated_record_without_model_slots(self):
        from ai_storage.models import BuyerMemory
        BuyerMemory.objects.create(owner_id=self.user.pk,
            preferences={'categories': ['绿茶'], 'brands': [], 'keywords': []})
        data = self.chat('推荐我偏好的商品', {'action': 'not-a-valid-model-action'}).json()
        self.assertEqual(data['intent_source'], 'rules')
        self.assertTrue(data['memory_used'])
        self.assertTrue(data['recommendations'])
        self.assertEqual(data['product_intent']['preferred']['categories'], ['绿茶'])
        self.assertEqual(data['product_intent']['required']['categories'], [])

    def test_missing_saved_preference_requests_details_without_product_query(self):
        with patch('support_ai.tool_services.match_products') as query:
            data = self.chat('推荐我偏好的商品').json()
        query.assert_not_called()
        self.assertTrue(data['clarification_required'])
        self.assertFalse(data['recommendations'])
        self.assertEqual([t['tool'] for t in data['tasks']], ['ask_clarification'])

    def test_foreign_conversation_is_rejected(self):
        from users.models import UserProfile
        from .models import SupportConversation
        other = UserProfile.objects.create(username='other-plan', password='unused', email='other@test.invalid', phone='')
        conversation = SupportConversation.objects.create(user=other)
        self.assertEqual(self.chat('推荐茶叶', conversation_id=str(conversation.pk)).status_code, 404)

    def test_order_followup_reloads_status_and_keeps_identity_private(self):
        from django.utils import timezone
        from orders.models import OrderInfo
        from .context import current_order_context
        from .models import SupportConversation
        order = OrderInfo.objects.create(order_id='ORDER-LOCAL-1', user_profile=self.user, total_amount='50',
            total_count=1, freight='0', status=1, receiver='测试', address='测试地址', receiver_mobile='13800138000', tag='')
        conversation = SupportConversation.objects.create(user=self.user, active_order_id=order.pk, active_order_at=timezone.now())
        order.status = 2
        order.save()
        message, context, selected = current_order_context(self.user, conversation, '那现在呢？')
        self.assertEqual(selected, order.pk)
        self.assertEqual(json.loads(context)[0]['status'], '待发货')
        self.assertNotIn(order.pk, context)
        self.assertNotIn(order.receiver_mobile, context)
        safe, _, selected = current_order_context(self.user, conversation, '订单号：ORDER-LOCAL-1')
        self.assertNotIn(order.pk, safe)
        self.assertEqual(selected, order.pk)

    def test_simple_slots_do_not_discard_budget_before_recommendation_verb(self):
        from .tool_services import simple_purchase_intent
        self.assertIsNone(simple_purchase_intent('预算每盒100美元，推荐绿茶', '推荐绿茶', [], None))
        history = [{'intent': 'recommendation', 'user_text': '预算每盒100美元'}]
        self.assertIsNone(simple_purchase_intent('推荐绿茶', '推荐绿茶', history, None))
