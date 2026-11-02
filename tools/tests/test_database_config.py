"""Configuration contracts; never open a database connection."""
import unittest

from tea_saas.database import database_config


class UnifiedDatabaseConfigTests(unittest.TestCase):
    def test_default_is_one_postgresql_connection(self):
        databases, alias = database_config({'POSTGRES_NAME':'synthetic', 'POSTGRES_PASSWORD':'fixture'})
        self.assertEqual(alias, 'default')
        self.assertEqual(set(databases), {'default'})
        self.assertEqual(databases['default']['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(databases['default']['NAME'], 'synthetic')
        self.assertNotIn('charset', databases['default']['OPTIONS'])

    def test_unified_never_infers_target_from_old_mysql_or_ai_database(self):
        databases, _ = database_config({'DB_NAME':'legacy-commerce','DB_PORT':'3306',
            'AI_POSTGRES_NAME':'legacy-knowledge'})
        self.assertEqual(databases['default']['NAME'], 'tea_saas')
        self.assertEqual(databases['default']['PORT'], 5433)

    def test_legacy_source_mode_is_explicit_and_keeps_both_sources(self):
        databases, alias = database_config({'TEA_SAAS_DATABASE_MODE':'legacy','DB_NAME':'old',
            'DB_USER':'source','DB_PASSWORD':'fixture','DB_HOST':'127.0.0.1','DB_PORT':'3306'})
        self.assertEqual(alias, 'ai_storage')
        self.assertEqual(set(databases), {'default','ai_storage'})
        self.assertEqual(databases['default']['ENGINE'], 'django.db.backends.mysql')

    def test_unknown_mode_fails_closed(self):
        with self.assertRaises(ValueError):
            database_config({'TEA_SAAS_DATABASE_MODE':'unfied'})

    def test_ai_alias_can_share_the_default_transaction(self):
        from unittest.mock import patch
        from ai_storage.database import alias
        from types import SimpleNamespace
        with patch('ai_storage.database.settings', new=SimpleNamespace(AI_STORAGE_DB_ALIAS='default')):
            self.assertEqual(alias(), 'default')
