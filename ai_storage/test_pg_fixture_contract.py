"""Disposable PostgreSQL admission and driver-free optional fixture setup; no real DB."""
from contextlib import contextmanager
from importlib import import_module
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import django.db


FIXTURES = (
    ('ai_storage.test_paddle_document_database', 'PaddleDocumentDatabaseTests',
     'AI_PADDLEOCR_TEST_DATABASE', 'paddle_document_test_'),
    ('ai_storage.test_vision_database', 'VisionDatabaseTests',
     'AI_VISION_TEST_DATABASE', 'vision_adapter_test_'),
)


class FixtureConnection:
    vendor = 'postgresql'

    def __init__(self, config, actual_name=None, may_query=True):
        self.settings_dict = config
        self.actual_name = actual_name if actual_name is not None else config['NAME']
        self.may_query = may_query

    @contextmanager
    def cursor(self):
        if not self.may_query:
            raise AssertionError('Unsafe configured targets must be rejected before connecting')
        connection = self

        class Cursor:
            def execute(self, sql):
                if sql != 'SELECT current_database()':
                    raise AssertionError('Unexpected identity query')

            def fetchone(self):
                return (connection.actual_name,)

        yield Cursor()


class FixtureConnections(dict):
    def close_all(self):
        pass  # No actual database connection is opened by these fixtures.


class DisposablePostgreSQLFixtureTests(unittest.TestCase):
    @contextmanager
    def fixture(self, definition, *, name=None, engine='django.db.backends.postgresql',
                actual_name=None, vendor='postgresql', extra_database=False, may_query=True, legacy_name=None):
        module_name, class_name, variable, prefix = definition
        name = name if name is not None else prefix + 'a' * 24
        config = {'ENGINE': engine, 'NAME': name}
        databases = {'default': config}
        if extra_database:
            databases['ai_storage'] = dict(config)
        configured = SimpleNamespace(DATABASES=databases, AI_STORAGE_DB_ALIAS='default')
        connection = FixtureConnection(config, actual_name, may_query)
        connection.vendor = vendor
        test_class = getattr(import_module(module_name), class_name)
        with patch.dict(os.environ, {variable: name, 'AI_POSTGRES_NAME': legacy_name or name}), \
                patch('django.setup'), patch('django.conf.settings', configured), \
                patch('ai_storage.database.settings', configured), \
                patch('django.db.connections', FixtureConnections(default=connection)), \
                patch('ai_storage.test_vision.VisionHttpFixture.setUpClass', classmethod(lambda cls: None)):
            yield test_class

    def test_unified_fixtures_accept_only_the_current_pg_target_without_legacy_ai_name(self):
        for definition in FIXTURES:
            with self.subTest(fixture=definition[1]), self.fixture(definition, legacy_name='retired_other_database') as test_class:
                try:
                    test_class.setUpClass()
                except Exception as exc:
                    self.fail('Unified PostgreSQL fixture was rejected: {}'.format(exc))
                else:
                    if hasattr(test_class, 'server'):
                        test_class.tearDownClass()

    def test_non_disposable_database_names_are_rejected_before_connecting(self):
        for definition in FIXTURES:
            for name in ('tea_saas', definition[3] + 'a' * 23, definition[3] + 'A' * 24):
                with self.subTest(fixture=definition[1], name=name), \
                        self.fixture(definition, name=name, may_query=False) as test_class:
                    with self.assertRaises(RuntimeError):
                        test_class.setUpClass()

    def test_other_engines_and_split_connections_are_rejected_before_connecting(self):
        for definition in FIXTURES:
            for options in ({'engine': 'django.db.backends.sqlite3'},
                            {'engine': 'django.db.backends.mysql'}, {'extra_database': True}):
                with self.subTest(fixture=definition[1], options=options), \
                        self.fixture(definition, may_query=False, **options) as test_class:
                    with self.assertRaises(RuntimeError):
                        test_class.setUpClass()

    def test_live_backend_and_database_name_must_match_the_disposable_pg_target(self):
        for definition in FIXTURES:
            for options in ({'actual_name': 'tea_saas'}, {'vendor': 'sqlite'}):
                with self.subTest(fixture=definition[1], options=options), \
                        self.fixture(definition, **options) as test_class:
                    with self.assertRaises(RuntimeError):
                        test_class.setUpClass()

    def test_both_optional_fixture_setups_work_with_mysql_imports_blocked(self):
        script = r'''
import importlib.abc
import importlib
import os
import sys
from unittest.mock import patch

class NoMySQL(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in ('MySQLdb', 'pymysql') or fullname.startswith('django.db.backends.mysql'):
            raise ImportError('MySQL dependencies are unavailable')

sys.meta_path.insert(0, NoMySQL())
for name in tuple(sys.modules):
    if name.split('.')[0] in ('MySQLdb', 'pymysql') or name.startswith('django.db.backends.mysql'):
        del sys.modules[name]
from django.db.backends.base.base import BaseDatabaseWrapper
with patch.object(BaseDatabaseWrapper, 'connect', side_effect=AssertionError('Real database access forbidden')):
    import django
    django.setup()
    from ai_storage.test_pg_fixture_contract import FIXTURES, FixtureConnection, FixtureConnections
    from django.conf import settings
    for module_name, class_name, variable, prefix in FIXTURES:
        name = prefix + 'a' * 24
        config = {'ENGINE': 'django.db.backends.postgresql', 'NAME': name}
        test_class = getattr(importlib.import_module(module_name), class_name)
        with patch.dict(os.environ, {variable: name}), \
                patch.object(settings, 'DATABASES', {'default': config}), \
                patch('django.db.connections', FixtureConnections(default=FixtureConnection(config))):
            test_class.setUpClass()
            instance = test_class(methodName='runTest')
            try:
                instance.setUp()
            finally:
                instance.doCleanups()
                if hasattr(test_class, 'server'):
                    test_class.tearDownClass()
'''
        environment = dict(os.environ, DJANGO_SETTINGS_MODULE='tea_saas.settings',
            DJANGO_ENV_FILE=os.devnull, DJANGO_POSTGRES_ENV_FILE=os.devnull,
            TEA_SAAS_DATABASE_MODE='unified', POSTGRES_NAME='fixture_only_no_connection',
            DJANGO_SECRET_KEY='fixture', JWT_SECRET_KEY='fixture', SUPPORT_API_KEY='fixture',
            SUPPORT_MODEL='fixture', SUPPORT_BASE_URL='http://127.0.0.1', ADMIN_INITIAL_PASSWORD='fixture',
            ALIPAY_PAY_URL='http://127.0.0.1', ALIPAY_APP_ID='fixture', ALIPAY_APP_PRIVATE_KEY='fixture',
            ALIPAY_APP_NOTIFY_URL='http://127.0.0.1', FRONTEND_BASE_URL='http://127.0.0.1')
        environment.pop('AI_POSTGRES_NAME', None)
        result = subprocess.run([sys.executable, '-c', script], cwd=Path(__file__).resolve().parents[1],
                                env=environment, text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)