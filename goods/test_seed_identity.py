"""A project rename must not relax database identity checks on write commands."""
from unittest.mock import MagicMock, patch

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from goods.management.commands.seed_virtual_tea_products import Command


class SeedIdentityTests(SimpleTestCase):
    def test_database_name_mismatch_prevents_writes(self):
        self.assert_identity_rejected(('unexpected', 'server-1'))

    def test_server_uuid_mismatch_prevents_writes(self):
        self.assert_identity_rejected(('expected', 'server-2'))

    def assert_identity_rejected(self, identity):
        connection = MagicMock(vendor='mysql')
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = identity
        with patch('goods.management.commands.seed_virtual_tea_products.connections', {'default': connection}), patch(
                'goods.management.commands.seed_virtual_tea_products.UserProfile') as users:
            with self.assertRaisesMessage(CommandError, 'Unexpected database identity; no rows were written'):
                Command().handle(database='default', batch='TEST', expected_database_name='expected',
                                 expected_server_uuid='server-1')
            users.objects.using.assert_not_called()
            cursor.execute.assert_called_once_with('SELECT DATABASE(), @@server_uuid')
