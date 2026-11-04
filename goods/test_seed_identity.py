"""Operator seeding requires the exact default PostgreSQL database and cluster."""
from contextlib import contextmanager
from unittest.mock import patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from goods.management.commands.seed_virtual_tea_products import Command


class IdentityConnection:
    def __init__(self, vendor='postgresql', identity=('expected', '7400000000000000001')):
        self.vendor = vendor
        self.identity = identity
        self.queries = []

    @contextmanager
    def cursor(self):
        connection = self

        class Cursor:
            def execute(self, sql):
                connection.queries.append(sql)

            def fetchone(self):
                return connection.identity

        yield Cursor()


class SeedIdentityTests(SimpleTestCase):
    options = {'database': 'default', 'batch': 'TEST', 'merchant_id': 1,
               'expected_database_name': 'expected', 'expected_server_uuid': '7400000000000000001'}

    def assert_identity_rejected(self, identity):
        connection = IdentityConnection(identity=identity)
        with patch('goods.management.commands.seed_virtual_tea_products.connections', {'default': connection}), patch(
                'goods.management.commands.seed_virtual_tea_products.UserProfile') as users:
            with self.assertRaisesMessage(CommandError, 'Unexpected database identity; no rows were written'):
                Command().handle(**self.options)
            users.objects.using.assert_not_called()
        self.assertEqual(connection.queries,
                         ['SELECT current_database(), system_identifier::text FROM pg_control_system()'])

    def test_postgresql_database_name_mismatch_prevents_writes(self):
        self.assert_identity_rejected(('unexpected', '7400000000000000001'))

    def test_postgresql_system_identifier_mismatch_prevents_writes(self):
        self.assert_identity_rejected(('expected', '7400000000000000002'))

    def test_matching_legacy_mysql_identity_is_rejected_before_any_query_or_write(self):
        connection = IdentityConnection(vendor='mysql')
        with patch('goods.management.commands.seed_virtual_tea_products.connections', {'default': connection}), patch(
                'goods.management.commands.seed_virtual_tea_products.UserProfile') as users:
            users.objects.using.return_value.filter.return_value.first.return_value = None
            with self.assertRaisesMessage(CommandError, 'PostgreSQL'):
                Command().handle(**self.options)
            users.objects.using.assert_not_called()
        self.assertEqual(connection.queries, [])

    def test_other_backends_are_rejected_before_any_query_or_write(self):
        for vendor in ('sqlite', ''):
            connection = IdentityConnection(vendor=vendor)
            with self.subTest(vendor=vendor), patch(
                    'goods.management.commands.seed_virtual_tea_products.connections', {'default': connection}), patch(
                    'goods.management.commands.seed_virtual_tea_products.UserProfile') as users:
                with self.assertRaises(CommandError):
                    Command().handle(**self.options)
                users.objects.using.assert_not_called()
            self.assertEqual(connection.queries, [])

    def test_non_default_alias_is_rejected_before_querying(self):
        connection = IdentityConnection()
        with patch('goods.management.commands.seed_virtual_tea_products.connections', {'other': connection}), patch(
                'goods.management.commands.seed_virtual_tea_products.UserProfile') as users:
            with self.assertRaises(CommandError):
                Command().handle(**dict(self.options, database='other'))
            users.objects.using.assert_not_called()
        self.assertEqual(connection.queries, [])

    def test_matching_postgresql_identity_reaches_merchant_validation_without_writing(self):
        connection = IdentityConnection()
        with patch('goods.management.commands.seed_virtual_tea_products.connections', {'default': connection}), patch(
                'goods.management.commands.seed_virtual_tea_products.UserProfile') as users:
            users.objects.using.return_value.filter.return_value.first.return_value = None
            with self.assertRaisesMessage(CommandError, 'An existing active merchant is required'):
                Command().handle(**self.options)
            users.objects.using.assert_called_once_with('default')
            users.objects.using.return_value.filter.assert_called_once_with(pk=1, user_type='merchant', is_active=True)
        self.assertEqual(connection.queries,
                         ['SELECT current_database(), system_identifier::text FROM pg_control_system()'])

    def test_previous_server_argument_names_both_accept_the_pg_system_identifier(self):
        parser = Command().create_parser('manage.py', 'seed_virtual_tea_products')
        for option in ('--expected-server-uuid', '--expected-server-id'):
            with self.subTest(option=option):
                parsed = parser.parse_args(['--merchant-id', '1', '--expected-database-name', 'expected',
                                           option, '7400000000000000001'])
                self.assertEqual(parsed.expected_server_uuid, '7400000000000000001')
