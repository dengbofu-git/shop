"""Synthetic order navigation regressions against an isolated database."""
import json
import uuid
from unittest.mock import patch

from django.test import TestCase

from orders.models import OrderInfo
from orders.support_links import support_order_reference
from tea_saas.utils import jwt_encode
from users.models import UserProfile
from .context import commit_turn, replay
from .conversation_history import history_value
from .order_contracts import rule_order_query
from .order_queries import OrderQueryContext, attach_order_links, query_orders


class OrderNavigationTests(TestCase):
    def setUp(self):
        redis = patch('orders.views.get_redis_connection')
        redis.start()
        self.addCleanup(redis.stop)
        self.buyer = UserProfile.objects.create(username='orderlink-buyer', user_type='customer', is_active=True)
        self.other = UserProfile.objects.create(username='orderlink-other', user_type='customer', is_active=True)
        self.own = [self.order(self.buyer, 'NAV-PRIVATE-{}'.format(i)) for i in range(3)]
        self.hidden = self.order(self.buyer, 'NAV-HIDDEN', hidden=True)
        self.foreign = self.order(self.other, 'NAV-FOREIGN')

    def order(self, owner, identity, hidden=False):
        return OrderInfo.objects.create(order_id=identity, user_profile=owner, total_amount='40.00',
            total_count=1, freight='0.00', status=1, receiver='Synthetic', address='Synthetic',
            receiver_mobile='00000000000', tag='Test', buyer_hidden=hidden)

    def query(self, message='查询最近订单'):
        context = OrderQueryContext(owner_id=self.buyer.pk)
        result = query_orders(rule_order_query(message), context, message)
        response = {'answer': result['data']['answer'], 'intent': 'after_sales',
                    'order_result': dict(result['data'], status=result['status'])}
        return result, context, attach_order_links(response, context)

    def headers(self, user):
        return {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': user.pk})}

    def test_order_facts_remain_anonymous_and_copy_is_concise(self):
        result, context, response = self.query()
        self.assertEqual(len(result['data']['orders']), 3)
        for phrase in ('最多', '请提供该订单号', '查询时间：'):
            self.assertNotIn(phrase, result['data']['answer'])
        self.assertIn('订单状态以订单详情为准', result['data']['answer'])
        self.assertTrue(result['data']['queried_at'])
        public = json.dumps(result, ensure_ascii=False)
        for order in self.own + [self.hidden, self.foreign]:
            self.assertNotIn(order.pk, public)
        self.assertNotIn('detail_url', public)  # Before model/audit completion.
        self.assertNotIn('os-', public)
        self.assertEqual(len(context.navigation_tokens), 3)
        self.assertEqual(len(response['order_result']['orders']), 3)

    def test_each_link_matches_exactly_one_current_owned_visible_order(self):
        _, _, response = self.query()
        data = self.client.get('/v1/orders/' + self.buyer.username, {'type': '0'}, **self.headers(self.buyer)).json()
        current = data['data']['orders_list']
        for order in response['order_result']['orders']:
            self.assertRegex(order['detail_url'], r'^/buyer_orders\.html#support-order=os-[a-p]{64}$')
            token = order['detail_url'].split('=', 1)[1]
            self.assertEqual(sum(row['support_reference'] == token for row in current), 1)
        ids = {row['order_id'] for row in current}
        self.assertEqual(ids, {o.pk for o in self.own})

    def test_cross_account_reference_does_not_select_any_of_its_own_orders(self):
        token = support_order_reference(self.buyer.pk, self.own[0].pk)
        data = self.client.get('/v1/orders/' + self.other.username, {'type': '0'}, **self.headers(self.other)).json()
        self.assertFalse(any(row['support_reference'] == token for row in data['data']['orders_list']))
        self.assertNotEqual(token, support_order_reference(self.other.pk, self.own[0].pk))
        denied = self.client.get('/v1/orders/' + self.buyer.username, {'type': '0'}, **self.headers(self.other))
        self.assertEqual(denied.status_code, 403)

    def test_hidden_order_stops_matching_existing_navigation(self):
        token = support_order_reference(self.buyer.pk, self.own[0].pk)
        OrderInfo.objects.filter(pk=self.own[0].pk).update(buyer_hidden=True)
        data = self.client.get('/v1/orders/' + self.buyer.username, {'type': '0'}, **self.headers(self.buyer)).json()
        self.assertFalse(any(row['support_reference'] == token for row in data['data']['orders_list']))

    def test_history_and_idempotent_replay_preserve_safe_navigation(self):
        _, _, response = self.query()
        self.assertEqual(history_value(response), response)
        request_id = uuid.uuid4()
        saved = commit_turn(self.buyer, None, 0, request_id, 'synthetic', '查询最近订单', response)
        self.assertEqual(replay(self.buyer, request_id, 'synthetic'), saved)
        history = self.client.get('/v1/support/conversations/' + saved['conversation_id'] + '/',
                                  **self.headers(self.buyer)).json()
        self.assertEqual(history['turns'][0]['response']['order_result'], response['order_result'])

    def test_payment_uncertainty_is_kept(self):
        result, _, _ = self.query('查询最近订单的付款状态')
        self.assertIn('不代表独立的支付到账核验', result['data']['answer'])

    def test_unavailable_results_do_not_get_navigation(self):
        context = OrderQueryContext(owner_id=self.buyer.pk)
        context.navigation_tokens = {'近期订单1': support_order_reference(self.buyer.pk, self.own[0].pk)}
        response = {'compliance_blocked': True, 'order_result': {'status': 'success',
                    'orders': [{'reference': '近期订单1'}]}}
        self.assertNotIn('detail_url', attach_order_links(response, context)['order_result']['orders'][0])
