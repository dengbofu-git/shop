"""Many-to-many human conversations, checked through authenticated HTTP and ORM."""
import json
from unittest import skipUnless

from django.db import connection
from django.test import Client, TestCase, TransactionTestCase

from tea_saas.utils import jwt_encode
from .models import Conversation, Message
from . import tests as fixtures


class ConversationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        fixtures.EngagementTests.setUpTestData.__func__(cls)

    make_sku = staticmethod(fixtures.EngagementTests.make_sku)
    call = fixtures.EngagementTests.call
    send = fixtures.EngagementTests.send

    def pairs(self):
        a = self.send(request='buyer-one-shop-one').json()['data']['conversation_id']
        b = self.send(sku=self.foreign, request='buyer-one-shop-two').json()['data']['conversation_id']
        c = self.send(user=self.other, request='buyer-two-shop-one').json()['data']['conversation_id']
        return a, b, c

    def test_each_account_lists_only_its_own_multiple_counterparties(self):
        a, b, c = self.pairs()
        for user, expected in ((self.buyer, [a, b]), (self.other, [c]),
                               (self.shop, [a, c]), (self.shop2, [b])):
            with self.subTest(user=user.username):
                data = self.call('conversations', user).json()['data']
                self.assertCountEqual([row['id'] for row in data['items']], expected)
                self.assertEqual(data['total'], len(expected))
        repeat = self.send(request='another-question').json()['data']['conversation_id']
        self.assertEqual(repeat, a)
        self.assertEqual(Conversation.objects.count(), 3)

    def test_merchant_replies_to_multiple_buyers_without_mixing_messages(self):
        a, b, c = self.pairs()
        for conv, text in ((a, '给第一位买家的回复'), (c, '给第二位买家的回复')):
            result = self.call('conversations/%s/messages' % conv, self.shop,
                               {'text': text, 'request_id': 'reply-to-%s' % conv})
            self.assertEqual(result.status_code, 201)
        for user, conv, expected in ((self.buyer, a, '给第一位买家的回复'),
                                    (self.other, c, '给第二位买家的回复')):
            data = self.call('conversations/%s/messages' % conv, user).json()['data']
            self.assertEqual(data['items'][-1]['text'], expected)
            self.assertFalse(data['items'][-1]['is_mine'])
            self.assertEqual(data['conversation_id'], conv)
            self.assertEqual(data['name'], self.shop.shop_name)
        self.assertEqual(Message.objects.filter(conversation_id=b).count(), 1)

    def test_pair_isolation_also_covers_accounts_with_other_valid_conversations(self):
        a, b, c = self.pairs()
        for user, conv in ((self.buyer, c), (self.other, a), (self.shop, b), (self.shop2, a)):
            mid = Message.objects.filter(conversation_id=conv).first().pk
            with self.subTest(user=user.username, conversation=conv):
                path = 'conversations/%s/' % conv
                self.assertEqual(self.call(path + 'messages', user).status_code, 404)
                self.assertEqual(self.call(path + 'messages', user,
                    {'text': '不可跨会话发送', 'request_id': 'forbidden-message'}).status_code, 404)
                self.assertEqual(self.call(path + 'read', user, {'message_id': mid}).status_code, 404)
        self.assertEqual(Message.objects.count(), 3)

    def test_messages_are_in_database_and_recovered_by_a_new_browser_session(self):
        a, b, c = self.pairs()
        saved = list(Message.objects.filter(conversation_id=a).values('id', 'text', 'sender_id'))
        self.assertEqual(saved[0]['sender_id'], self.buyer.pk)
        # New Client has neither the previous client's cookies nor browser storage.
        self.client = Client()
        data = self.call('conversations/%s/messages' % a, self.shop).json()['data']
        self.assertEqual([(row['id'], row['text']) for row in data['items']],
                         [(row['id'], row['text']) for row in saved])
        self.assertEqual(data['name'], self.buyer.username[:1] + '***')
        self.assertNotIn(self.buyer.username, json.dumps(data))

    def test_unread_and_receipts_are_independent_for_each_pair(self):
        a, b, c = self.pairs()
        mid = Message.objects.filter(conversation_id=a).first().pk
        self.call('conversations/%s/read' % a, self.shop, {'message_id': mid})
        self.client = Client()
        rows = self.call('conversations', self.shop).json()['data']
        self.assertEqual(rows['unread_total'], 1)
        self.assertEqual({row['id']: row['unread'] for row in rows['items']}, {a: 0, c: 1})
        self.assertEqual(Conversation.objects.get(pk=a).merchant_read_id, mid)
        self.assertEqual(Conversation.objects.get(pk=c).merchant_read_id, 0)
        self.assertEqual(Conversation.objects.get(pk=b).merchant_read_id, 0)


@skipUnless(connection.vendor == 'mysql', 'Requires an isolated persistent MySQL database')
class ConversationPersistenceTests(TransactionTestCase):
    make_sku = staticmethod(fixtures.EngagementTests.make_sku)

    def test_committed_messages_survive_closing_and_reopening_database_connection(self):
        fixtures.EngagementTests.setUpTestData.__func__(type(self))
        headers = {'HTTP_AUTHORIZATION': jwt_encode({'id': self.buyer.pk})}
        response = Client().post('/v1/engagement/conversations', json.dumps({
            'merchant_id': self.shop.pk, 'text': '重连数据库后仍然保存的咨询',
            'request_id': 'durable-message-01'}), content_type='application/json', **headers)
        self.assertEqual(response.status_code, 201)
        data = response.json()['data']
        conversation_id, message_id = data['conversation_id'], data['message']['id']
        self.assertTrue(connection.get_autocommit())
        connection.close()
        self.assertEqual(Message.objects.get(pk=message_id).text, '重连数据库后仍然保存的咨询')
        result = Client().get('/v1/engagement/conversations/%s/messages' % conversation_id, **headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['data']['items'][0]['id'], message_id)
