"""Upgrade a pre-existing conversation inside the isolated test database only."""
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from users.models import UserProfile

from .models import Conversation, Message


class VisibilityMigrationTests(TransactionTestCase):
    def test_upgrade_preserves_existing_pairs_and_messages_visible_to_both_sides(self):
        before = [('engagement', '0001_initial')]
        after = [('engagement', '0002_conversation_visibility')]
        buyer = UserProfile.objects.create(username='migbuyer', is_active=True)
        shop = UserProfile.objects.create(username='migshop', user_type='merchant', is_active=True)
        executor = MigrationExecutor(connection)
        executor.migrate(before)
        try:
            apps = executor.loader.project_state(before).apps
            conv = apps.get_model('engagement', 'Conversation').objects.create(buyer_id=buyer.pk, merchant_id=shop.pk)
            message = apps.get_model('engagement', 'Message').objects.create(
                conversation=conv, sender_id=buyer.pk, text='迁移前的咨询', request_id='migration-message', fingerprint='test')
        finally:
            MigrationExecutor(connection).migrate(after)
        restored = Conversation.objects.get(pk=conv.pk)
        self.assertFalse(restored.buyer_hidden)
        self.assertFalse(restored.merchant_hidden)
        self.assertEqual(restored.buyer_id, buyer.pk)
        self.assertEqual(Message.objects.get(pk=message.pk).text, '迁移前的咨询')
