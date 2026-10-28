"""Regression from the buyer's exact input through real synthetic SKU search."""
from decimal import Decimal
import uuid
from unittest.mock import patch

from django.test import TestCase

from goods.models import Catalog, SPU, SKU
from users.models import UserProfile
from .mcp_testing import create_tool_handlers
from .workflow import build_graph
from .context import commit_turn, recent_context
from .models import SupportConversation


class GenericTeaBudgetTests(TestCase):
    def setUp(self):
        merchant = UserProfile.objects.create(username='synthetic-budget-shop', user_type='merchant', is_active=True)
        category = Catalog.objects.create(name='红茶')
        for index, price in enumerate(('750.00', '600.00')):
            product = SPU.objects.create(name='合成预算茶{}'.format(index), catalog=category, merchant=merchant)
            SKU.objects.create(spu=product, name='合成规格', price=price, market_price=price,
                               cost_price='100.00', stock=10, is_launched=True)

    def graph(self):
        def factory(state):
            return create_tool_handlers(None, None, state['safe_message'], state['resolved_question'],
                                        state.get('recent_turns', []), None)

        return build_graph(None, tool_factory=factory)

    def test_exact_buyer_sentence_produces_checked_three_thousand_yuan_bundle(self):
        response = self.graph().invoke({'message': '推荐总价为3000块的茶'})['response']
        self.assertEqual(response['intent_source'], 'rules')
        self.assertEqual(response['tasks'], [{'id': 's1', 'tool': 'recommend_bundle', 'status': 'success'}])
        self.assertEqual(response['product_intent']['required']['budget_max'], '3000.00')
        self.assertEqual(response['product_intent']['required']['currency'], 'CNY')
        self.assertEqual(response['recommendation_status'], 'MATCHED')
        self.assertFalse(response['clarification_required'])
        self.assertEqual(response['diagnostics'], [])
        self.assertEqual(response['recommendation_bundles'][0]['subtotal'], '3000.00')
        self.assertTrue(any(item['quantity'] > 1 for item in response['recommendation_bundles'][0]['items']))
        for bundle in response['recommendation_bundles']:
            subtotal = sum(Decimal(item['price']) * item['quantity'] for item in bundle['items'])
            self.assertEqual(subtotal, Decimal(bundle['subtotal']))
            self.assertLessEqual(subtotal, Decimal('3000.00'))
            for item in bundle['items']:
                self.assertEqual(Decimal(item['line_subtotal']), Decimal(item['price']) * item['quantity'])

    def pending(self):
        user = UserProfile.objects.create(username='synthetic-budget-buyer', user_type='customer', is_active=True)
        message = '推荐3000块的茶'
        response = self.graph().invoke({'message': message})['response']
        self.assertTrue(response['clarification_required'])
        saved = commit_turn(user, None, 0, uuid.uuid4(), 'synthetic-first', message, response)
        return user, SupportConversation.objects.get(pk=saved['conversation_id'])

    def assert_total_succeeds(self, response):
        self.assertEqual(response['tasks'][0]['tool'], 'recommend_bundle')
        self.assertEqual(response['tasks'][0]['status'], 'success')
        self.assertEqual(response['product_intent']['required']['budget_max'], '3000.00')
        self.assertEqual(response['product_intent']['required']['currency'], 'CNY')
        self.assertFalse(response['clarification_required'])
        self.assertEqual(response['diagnostics'], [])
        self.assertEqual(response['recommendation_bundles'][0]['subtotal'], '3000.00')

    def test_package_reply_reuses_budget_through_saved_http_style_context(self):
        _, conversation = self.pending()
        response = self.graph().invoke({'message': '套餐', 'recent_turns': recent_context(conversation)})['response']
        self.assert_total_succeeds(response)

    def test_whole_set_reply_recovers_after_an_intervening_legacy_failure(self):
        user, conversation = self.pending()
        with patch('support_ai.workflow.plan_turn', side_effect=ValueError('legacy scope failure')):
            failed = self.graph().invoke({'message': '套餐', 'recent_turns': recent_context(conversation)})['response']
        self.assertEqual(failed['dialogue_state']['status'], 'pending')
        commit_turn(user, conversation, 1, uuid.uuid4(), 'synthetic-failed', '套餐', failed)
        response = self.graph().invoke({'message': '整套', 'recent_turns': recent_context(conversation)})['response']
        self.assert_total_succeeds(response)

    def test_explicit_package_noun_uses_real_bundle_search(self):
        response = self.graph().invoke({'message': '推荐总价3000块的套餐'})['response']
        self.assert_total_succeeds(response)
