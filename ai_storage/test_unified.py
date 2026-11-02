"""The single-database topology must support real cross-module transactions."""
from unittest import skipUnless
from django.db import connection, transaction
from django.test import TestCase
from ai_storage.database import alias
from ai_storage.models import BuyerMemory
from users.models import UserProfile


@skipUnless(alias() == 'default' and connection.vendor == 'postgresql', 'requires unified PostgreSQL')
class UnifiedStorageTests(TestCase):
    def test_transfer_refuses_to_round_legacy_money(self):
        from tools.database_transfer import read_rows, TransferError
        with connection.cursor() as cursor:
            cursor.execute('CREATE TEMP TABLE money_precision_fixture (amount numeric(10,3)) ON COMMIT DROP')
            cursor.execute('INSERT INTO money_precision_fixture VALUES (1.234)')
        with self.assertRaises(TransferError):
            read_rows(connection, {'table':'money_precision_fixture','columns':[
                {'name':'amount','kind':'decimal','scale':2}]})

    def test_knowledge_services_use_the_only_configured_connection(self):
        from ai_storage.knowledge import hybrid_search_ready
        self.assertTrue(hybrid_search_ready())

    def test_ai_and_business_changes_rollback_together(self):
        with self.assertRaises(ValueError):
            with transaction.atomic():
                user = UserProfile.objects.create(username='pgrollback', is_active=True)
                BuyerMemory.objects.create(owner_id=user.pk, preferences={'categories':['绿茶']})
                raise ValueError('synthetic rollback')
        self.assertFalse(UserProfile.objects.filter(username='pgrollback').exists())
        self.assertFalse(BuyerMemory.objects.exists())
