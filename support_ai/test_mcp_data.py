"""MCP-only boundary, grant, failure and delegation regressions; synthetic data."""
import json
from unittest.mock import patch

from django.test import TestCase, SimpleTestCase

from goods.models import Catalog, SPU, SKU
from users.models import UserProfile
from .mcp_client import AgentDataAccess, McpServiceError
from .mcp_security import verify_grant, issue_grant, AccessDenied
from .mcp_testing import SyntheticMcpTransport, config
from .cost_control import RequestBudget, CostPolicy
from .models import SupportConversation
from .order_queries import OrderQueryContext
from .order_contracts import rule_order_query


class McpDataTests(TestCase):
    databases = {'default','ai_storage'}

    def setUp(self):
        self.user = UserProfile.objects.create(username='mcp-buyer', user_type='customer', is_active=True)
        self.other = UserProfile.objects.create(username='mcp-other', user_type='customer', is_active=True)
        category = Catalog.objects.create(name='绿茶')
        merchant = UserProfile.objects.create(username='synthetic-active-seller', user_type='merchant', is_active=True)
        product = SPU.objects.create(name='合成协议茶', catalog=category, merchant=merchant)
        self.sku = SKU.objects.create(name='50克', spu=product, price='12.30', cost_price='1', market_price='15', stock=4)
        transport = patch('support_ai.mcp_client.StdioMcpTransport', SyntheticMcpTransport)
        transport.start()
        self.addCleanup(transport.stop)

    def access(self, **kwargs):
        access = AgentDataAccess(config=config(), message=kwargs.pop('message','推荐绿茶'), owner_id=self.user.pk, **kwargs)
        self.addCleanup(access.close)
        return access

    def test_public_read_uses_protocol_and_strict_arguments(self):
        access = self.access()
        result = access.call('get_product_details', sku_id=self.sku.pk)
        self.assertEqual(result['data']['price'], '12.30')
        self.assertEqual(access.transport.calls[0]['name'],'get_product_details')
        with self.assertRaises(ValueError):
            access.call('get_product_details', sku_id=self.sku.pk, owner_id=self.other.pk)

    def test_forged_expired_and_replayed_grants_fail_closed(self):
        access = self.access()
        token = access.environment['TEA_SAAS_AGENT_GRANT']
        with self.assertRaises(AccessDenied):
            verify_grant(token + 'changed')
        grant = verify_grant(token, claim=False)
        grant['expires_at'] = 0
        with self.assertRaises(AccessDenied):
            verify_grant(issue_grant(grant))
        verify_grant(token)
        with self.assertRaises(AccessDenied):
            verify_grant(token)

    def test_foreign_conversation_and_disabled_buyer_never_supply_context(self):
        foreign = SupportConversation.objects.create(user=self.other)
        with self.assertRaises(McpServiceError) as caught:
            self.access(conversation=foreign).history()
        self.assertEqual(caught.exception.code,'ACCESS_DENIED')
        access = self.access()
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        with self.assertRaises(McpServiceError) as caught:
            access.call('get_product_details', sku_id=self.sku.pk)
        self.assertEqual(caught.exception.code,'ACCESS_DENIED')

    def test_unprojected_backend_fields_are_rejected_before_model_consumption(self):
        access = self.access()
        from .mcp_backend import get_product_details
        payload = get_product_details(self.sku.pk)
        payload['data']['cost_price'] = 'private'
        with patch('support_ai.mcp_backend.get_product_details',return_value=payload):
            with self.assertRaises(McpServiceError) as caught:
                access.call('get_product_details',sku_id=self.sku.pk)
        self.assertEqual(caught.exception.code,'INVALID_BACKEND_RESPONSE')

    def test_revision_change_is_a_conflict_rather_than_a_missing_conversation(self):
        conversation = SupportConversation.objects.create(user=self.user,revision=1)
        access = self.access(conversation=conversation)
        SupportConversation.objects.filter(pk=conversation.pk).update(revision=2)
        with self.assertRaises(McpServiceError) as caught:
            access.history()
        self.assertEqual(caught.exception.code,'CONVERSATION_CONFLICT')

    def test_backend_failure_does_not_poison_independent_tool_or_next_request(self):
        access = self.access()
        with patch('support_ai.mcp_backend.saved_preferences', side_effect=RuntimeError('private secret')):
            with self.assertRaises(McpServiceError) as caught:
                access.preferences()
        self.assertNotIn('private secret', str(caught.exception))
        self.assertEqual(access.call('get_product_details', sku_id=self.sku.pk)['status'], 'success')
        self.assertIsNone(self.access().preferences())

    def test_order_private_effects_are_separate_from_mcp_result(self):
        from orders.models import OrderInfo
        order = OrderInfo.objects.create(order_id='MCP-PRIVATE-ORDER', user_profile=self.user,
            total_amount='12.30', total_count=1, freight='0', status=1, receiver='Private',
            address='Private', receiver_mobile='00000000000', tag='Test')
        context = OrderQueryContext(owner_id=self.user.pk)
        access = self.access(message='查询最近订单', order_context=context)
        result = access.call('get_order_status', query=rule_order_query('查询最近订单'), request='查询最近订单')
        encoded = json.dumps(result)
        self.assertNotIn(order.pk, encoded)
        self.assertNotIn('navigation_tokens', encoded)
        self.assertTrue(context.navigation_tokens)

    def test_host_never_queries_orm_for_data_when_transport_is_unavailable(self):
        access = self.access()
        with patch('support_ai.mcp_client.StdioMcpTransport', side_effect=McpServiceError('BACKEND_TIMEOUT')), \
             patch('support_ai.mcp_backend.get_product_details') as backend:
            with self.assertRaises(McpServiceError):
                access.call('get_product_details', sku_id=self.sku.pk)
        backend.assert_not_called()

    def test_explicit_preference_dependency_fails_without_committing_or_calling_model(self):
        from tea_saas.utils import jwt_encode
        from .models import SupportTurn
        headers = {'HTTP_AUTHORIZATION':'Bearer ' + jwt_encode({'id':self.user.pk})}
        with patch('support_ai.mcp_backend.saved_preferences',side_effect=RuntimeError('private error')), \
             patch('support_ai.model_client.configured_model') as model:
            response = self.client.post('/v1/support/chat/',data=json.dumps({'message':'按我保存的偏好推荐绿茶'}),
                                        content_type='application/json',**headers)
        self.assertEqual(response.status_code,503)
        self.assertFalse(SupportTurn.objects.filter(user=self.user).exists())
        model.assert_not_called()

    def test_unqueryable_order_does_not_cancel_independent_recommendation(self):
        from tea_saas.utils import jwt_encode
        from orders.models import OrderInfo
        OrderInfo.objects.create(order_id='MCP-FOREIGN',user_profile=self.other,total_amount='10',total_count=1,
            freight='0',status=1,receiver='Private',address='Private',receiver_mobile='000',tag='Test')
        from .test_task_tools import ToolModel
        from .semantic_planning import SemanticPlan, DialogueState
        from .planning import explicit_requests
        def known_plan(model,message,history,memory):
            return (SemanticPlan(action='new_request',standalone_question=message,
                    requests=explicit_requests(message)), 'rules', DialogueState())
        headers = {'HTTP_AUTHORIZATION':'Bearer ' + jwt_encode({'id':self.user.pk})}
        with patch('support_ai.model_client.configured_model',return_value=ToolModel()), \
             patch('support_ai.workflow.plan_turn',side_effect=known_plan):
            response = self.client.post('/v1/support/chat/',data=json.dumps({'message':'查询订单号：MCP-FOREIGN，并推荐绿茶'}),
                                        content_type='application/json',**headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['completion_status'],'partial',response.json())
        self.assertEqual([t['status'] for t in response.json()['tasks']],['error','success'])
        self.assertTrue(response.json()['recommendations'])


class DelegatedBudgetTests(SimpleTestCase):
    def test_remote_usage_consumes_same_request_budget(self):
        budget = RequestBudget(CostPolicy(3,1000,500))
        allocated = budget.delegate()
        self.assertEqual(budget.calls,3)
        remote = RequestBudget(CostPolicy(**allocated['policy']))
        reservation = remote.reserve('rewrite',100,50)
        remote.settle(reservation,{'input_tokens':70,'output_tokens':20})
        budget.settle_delegation(allocated,remote.snapshot())
        self.assertEqual((budget.calls,budget.input_tokens,budget.output_tokens),(1,70,20))

    def test_unknown_remote_usage_is_not_free_capacity(self):
        budget = RequestBudget(CostPolicy(3,1000,500))
        budget.settle_delegation(budget.delegate(),None)
        self.assertEqual((budget.calls,budget.input_tokens,budget.output_tokens),(3,1000,500))


class RequestScopeFailureTests(SimpleTestCase):
    def test_auth_and_revision_errors_are_not_optional_or_partially_completed(self):
        from types import SimpleNamespace
        from .views import load_agent_preferences
        from .execution import execute_plan
        from .planning import build_plan, IntentRequest
        plan = build_plan([IntentRequest(kind='question_answering',quote='介绍绿茶'),
                           IntentRequest(kind='recommendation',quote='推荐绿茶')], 'rules', '介绍绿茶，推荐绿茶')
        for code in ('ACCESS_DENIED','CONVERSATION_CONFLICT'):
            def refused(*args):
                raise McpServiceError(code)
            with self.assertRaises(McpServiceError):
                load_agent_preferences(SimpleNamespace(preferences=refused),'推荐绿茶',[])
            with self.assertRaises(McpServiceError):
                execute_plan(plan,{'introduce_tea':refused,
                    'recommend_products':lambda *args:self.fail('Request-scope failure continued execution')})
