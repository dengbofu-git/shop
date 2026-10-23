"""Manual inbox ordering is bounded, participant-scoped and paginated on the server."""
from django.test import TestCase
from users.models import UserProfile
from .models import Conversation
from .tests import EngagementTests


class ConversationOrderingTests(TestCase):
    setUpTestData = classmethod(EngagementTests.setUpTestData.__func__)
    make_sku = staticmethod(EngagementTests.make_sku)
    call = EngagementTests.call

    def setUp(self):
        self.first = Conversation.objects.create(buyer=self.buyer, merchant=self.shop)
        self.second = Conversation.objects.create(buyer=self.buyer, merchant=self.shop2)
        self.foreign = Conversation.objects.create(buyer=self.other, merchant=self.shop)

    def test_manual_order_survives_new_message_timestamp_without_mutating_other_side(self):
        path = 'conversations?order=%s,%s' % (self.first.pk, self.second.pk)
        result = self.call(path, self.buyer).json()['data']
        self.assertEqual([row['id'] for row in result['items']], [self.first.pk, self.second.pk])
        # Preferences are request-local, never an update to the pair or its timestamps.
        ordinary = self.call('conversations', self.buyer).json()['data']
        self.assertEqual([row['id'] for row in ordinary['items']], [self.second.pk, self.first.pk])
        other_side = self.call('conversations', self.shop).json()['data']
        self.assertEqual([row['id'] for row in other_side['items']], [self.foreign.pk, self.first.pk])

    def test_foreign_hidden_and_stale_ids_never_expand_visibility(self):
        Conversation.objects.filter(pk=self.first.pk).update(buyer_hidden=True)
        result = self.call('conversations?order=%s,%s,%s,999999' % (
            self.foreign.pk, self.first.pk, self.second.pk), self.buyer).json()['data']
        self.assertEqual([row['id'] for row in result['items']], [self.second.pk])
        self.assertEqual(result['total'], 1)

    def test_invalid_or_unbounded_sort_input_is_rejected(self):
        for value in ('1,1', '1,', '-1', '1.5', 'text', '9' * 19, ','.join(str(n) for n in range(1, 202))):
            self.assertEqual(self.call('conversations?order=' + value, self.buyer).status_code, 400)

    def test_manual_order_is_applied_before_pagination(self):
        for n in range(22):
            shop = UserProfile.objects.create(username='sortshop%s' % n, user_type='merchant', is_active=True)
            Conversation.objects.create(buyer=self.buyer, merchant=shop)
        ids = list(Conversation.objects.filter(buyer=self.buyer).order_by('id').values_list('id', flat=True))
        query = ','.join(str(n) for n in ids)
        first = self.call('conversations?order=' + query, self.buyer).json()['data']
        second = self.call('conversations?page=2&order=' + query, self.buyer).json()['data']
        self.assertEqual([row['id'] for row in first['items']] + [row['id'] for row in second['items']], ids)
