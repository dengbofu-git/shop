"""Participant-local inbox hiding preserves the conversation and its messages."""
from django.test import Client, TestCase

from supplier.workbench import build_workbench_feed
from .models import Conversation, Message
from .tests import EngagementTests


class ConversationVisibilityTests(TestCase):
    setUpTestData = classmethod(EngagementTests.setUpTestData.__func__)
    make_sku = staticmethod(EngagementTests.make_sku)
    call = EngagementTests.call
    send = EngagementTests.send

    def create_conversation(self):
        return self.send().json()['data']['conversation_id']

    def listed(self, user):
        return self.call('conversations', user).json()['data']

    def action(self, conv, user, action='hide'):
        return self.call('conversations/%s/%s' % (conv, action), user, {})

    def test_hiding_is_persistent_local_and_preserves_history_and_receipts(self):
        conv = self.create_conversation()
        self.assertEqual(self.listed(self.shop)['unread_total'], 1)
        self.assertEqual(self.action(conv, self.shop).status_code, 200)
        self.assertEqual(self.action(conv, self.shop).status_code, 200)
        # A fresh HTTP client reads the persisted flag, not a browser storage value.
        self.client = Client()
        self.assertEqual(self.listed(self.shop)['items'], [])
        self.assertEqual(self.listed(self.shop)['unread_total'], 0)
        self.assertEqual(self.listed(self.buyer)['total'], 1)
        history = self.call('conversations/%s/messages' % conv, self.buyer)
        self.assertEqual(len(history.json()['data']['items']), 1)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)
        record = Conversation.objects.get(pk=conv)
        self.assertTrue(record.merchant_hidden)
        self.assertFalse(record.buyer_hidden)
        self.assertEqual(record.merchant_read_id, 0)
        hidden = self.call('conversations/%s/messages' % conv, self.shop)
        self.assertEqual(hidden.status_code, 404)
        self.assertEqual(hidden.json()['error_code'], 'CONVERSATION_HIDDEN')
        feed = build_workbench_feed(self.shop)
        self.assertEqual(feed['todos']['consultations'], 0)
        self.assertFalse(any(row['kind'] == 'inquiry' for row in feed['messages']))

    def test_new_message_resurfaces_both_sides_with_full_history(self):
        conv = self.create_conversation()
        for user in (self.buyer, self.shop):
            self.action(conv, user)
        result = self.call('conversations/%s/messages' % conv, self.shop,
                           {'text': '欢迎继续聊茶', 'request_id': 'visibility-reply-01'})
        self.assertEqual(result.status_code, 201)
        for user in (self.buyer, self.shop):
            self.assertEqual(self.listed(user)['total'], 1)
            history = self.call('conversations/%s/messages' % conv, user).json()['data']
            self.assertEqual(len(history['items']), 2)
        self.assertEqual(Conversation.objects.count(), 1)

    def test_idempotent_retry_does_not_resurface_or_duplicate(self):
        conv = self.create_conversation()
        self.action(conv, self.buyer)
        self.action(conv, self.shop)
        self.assertEqual(self.send().status_code, 200)
        self.assertEqual(self.listed(self.buyer)['total'], 0)
        self.assertEqual(self.listed(self.shop)['total'], 0)
        self.assertEqual(Message.objects.count(), 1)
        self.assertEqual(self.send(request='visibility-new-01').status_code, 201)
        self.assertEqual(self.listed(self.buyer)['total'], 1)

    def test_explicit_restore_is_local_and_resolve_and_reads_do_not_restore(self):
        conv = self.create_conversation()
        for user in (self.buyer, self.shop):
            self.action(conv, user)
        resolved = self.call('conversations/resolve?sku_id=%s' % self.sku.pk, self.buyer)
        self.assertEqual(resolved.json()['data']['conversation_id'], conv)
        self.assertEqual(self.listed(self.buyer)['total'], 0)
        self.assertEqual(self.action(conv, self.buyer, 'restore').status_code, 200)
        self.assertEqual(self.listed(self.buyer)['total'], 1)
        self.assertEqual(self.listed(self.shop)['total'], 0)
        self.assertEqual(Message.objects.count(), 1)

    def test_cannot_hide_or_restore_another_participants_conversation(self):
        conv = self.create_conversation()
        for user in (self.other, self.shop2):
            for action in ('hide', 'restore'):
                self.assertEqual(self.action(conv, user, action).status_code, 404)
        for action in ('hide', 'restore'):
            self.assertEqual(self.action(conv, None, action).status_code, 401)
            self.assertEqual(self.action(conv, self.admin, action).status_code, 403)
            self.assertEqual(self.call('conversations/%s/%s' % (conv, action), self.buyer).status_code, 405)
        self.assertFalse(Conversation.objects.get(pk=conv).buyer_hidden)

    def test_hiding_one_pair_does_not_change_other_pairs_or_cursors(self):
        conv = self.create_conversation()
        other = self.send(sku=self.foreign, request='visibility-other-shop').json()['data']['conversation_id']
        self.action(conv, self.buyer)
        self.assertEqual([r['id'] for r in self.listed(self.buyer)['items']], [other])
        self.assertEqual(self.listed(self.shop)['total'], 1)
        self.assertEqual(self.listed(self.shop2)['total'], 1)
