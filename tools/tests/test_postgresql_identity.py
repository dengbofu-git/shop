"""PostgreSQL target guards and replay CLI admission; no database or model calls."""
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from importlib import import_module
from io import StringIO
from pathlib import Path
import os
import sys
from tempfile import TemporaryDirectory
from types import ModuleType
import unittest
from unittest.mock import patch


class FixtureConnection:
    vendor = 'postgresql'

    def __init__(self, row=('synthetic_replay', '7400000000000000001'), error=None):
        self.row = row
        self.error = error

    @contextmanager
    def cursor(self):
        connection = self

        class Cursor:
            def execute(self, sql):
                if sql != 'SELECT current_database(), system_identifier::text FROM pg_control_system()':
                    raise AssertionError('Unexpected identity query')
                if connection.error:
                    raise connection.error

            def fetchone(self):
                return connection.row

        yield Cursor()


class PostgreSQLIdentityTests(unittest.TestCase):
    def test_identity_reads_the_database_and_postgresql_cluster(self):
        from tools.postgresql_identity import database_identity
        self.assertEqual(database_identity(FixtureConnection()),
                         ('synthetic_replay', '7400000000000000001'))

    def test_other_backends_are_rejected_without_a_query(self):
        from tools.postgresql_identity import database_identity
        for vendor in ('mysql', 'sqlite', ''):
            connection = FixtureConnection(error=AssertionError('Must not query another backend'))
            connection.vendor = vendor
            with self.subTest(vendor=vendor), self.assertRaises(RuntimeError):
                database_identity(connection)

    def test_exact_identity_is_required(self):
        from tools.postgresql_identity import require_database_identity
        self.assertEqual(require_database_identity(FixtureConnection(), 'synthetic_replay', '7400000000000000001'),
                         ('synthetic_replay', '7400000000000000001'))
        for expected_database, expected_system_identifier in (
                ('other_database', '7400000000000000001'),
                ('synthetic_replay', '7400000000000000002'),
                ('SYNTHETIC_REPLAY', '7400000000000000001')):
            with self.subTest(database=expected_database, cluster=expected_system_identifier):
                with self.assertRaises(RuntimeError):
                    require_database_identity(FixtureConnection(), expected_database, expected_system_identifier)

    def test_missing_expected_identity_is_rejected_before_querying(self):
        from tools.postgresql_identity import require_database_identity
        for expected_database, expected_system_identifier in (
                ('', '7400000000000000001'), ('synthetic_replay', ''),
                (None, '7400000000000000001'), ('synthetic_replay', None)):
            connection = FixtureConnection(error=AssertionError('Missing identity must fail before querying'))
            with self.subTest(database=expected_database, cluster=expected_system_identifier):
                with self.assertRaises(RuntimeError):
                    require_database_identity(connection, expected_database, expected_system_identifier)

    def test_missing_or_malformed_server_identity_is_rejected(self):
        from tools.postgresql_identity import database_identity
        for row in (None, (), ('synthetic_replay',), ('synthetic_replay', None),
                    ('synthetic_replay', ''), ('', '7400000000000000001')):
            with self.subTest(row=row), self.assertRaises(RuntimeError):
                database_identity(FixtureConnection(row=row))

    def test_identity_query_failure_is_not_treated_as_a_match(self):
        from tools.postgresql_identity import require_database_identity
        connection = FixtureConnection(error=PermissionError('Synthetic permission denial'))
        with self.assertRaises(PermissionError):
            require_database_identity(connection, 'synthetic_replay', '7400000000000000001')


class ReplayIdentityAdmissionTests(unittest.TestCase):
    modules = ('support_ai.evaluation.compare', 'support_ai.evaluation.compare_rag_rewrite')

    def cli(self, module, arguments):
        replay = import_module(module)
        django = ModuleType('django')
        def forbidden_setup():
            raise AssertionError('CLI admission must finish before Django setup')
        django.setup = forbidden_setup
        stdout, stderr = StringIO(), StringIO()
        with patch.dict(sys.modules, {'django': django}), patch.object(sys, 'argv', [module, *arguments]):
            with redirect_stdout(stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as stopped:
                replay.main()
        return stopped.exception.code, stdout.getvalue(), stderr.getvalue()

    def test_both_cli_help_pages_expose_the_cluster_identity(self):
        for module in self.modules:
            with self.subTest(module=module):
                code, stdout, stderr = self.cli(module, ['--help'])
                self.assertEqual(code, 0, stderr)
                self.assertIn('--expected-system-identifier', stdout)

    def test_both_clis_require_the_cluster_identity_without_loading_django(self):
        for module in self.modules:
            arguments = ['--expected-database-name', 'synthetic_replay']
            if module.endswith('compare_rag_rewrite'):
                arguments += ['--output-dir', 'unused-synthetic-output']
            with self.subTest(module=module):
                code, stdout, stderr = self.cli(module, arguments)
                self.assertEqual(code, 2, stderr)
                self.assertIn('--expected-system-identifier', stderr)

    def test_frozen_comparator_remains_disabled_after_valid_arguments(self):
        replay = import_module('support_ai.evaluation.compare')
        arguments = ['compare', '--expected-database-name', 'synthetic_replay',
                     '--expected-system-identifier', '7400000000000000001']
        with patch.object(sys, 'argv', arguments), self.assertRaisesRegex(RuntimeError, 'frozen'):
            replay.main()

    def test_rag_replay_rejects_the_wrong_cluster_before_app_reads_or_output(self):
        replay = import_module('support_ai.evaluation.compare_rag_rewrite')
        django = ModuleType('django')
        django.setup = lambda: None
        database = ModuleType('django.db')
        database.connection = FixtureConnection(row=('synthetic_replay', '7400000000000000002'))
        with TemporaryDirectory() as folder:
            output = Path(folder) / 'must-not-exist'
            arguments = ['compare_rag_rewrite', '--output-dir', str(output),
                         '--expected-database-name', 'synthetic_replay',
                         '--expected-system-identifier', '7400000000000000001']
            with (patch.dict(os.environ, {'DJANGO_SETTINGS_MODULE': 'synthetic_unused_settings'}),
                  patch.dict(sys.modules, {'django': django, 'django.db': database}),
                  patch.object(sys, 'argv', arguments)):
                with self.assertRaises(RuntimeError):
                    replay.main()
            self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
