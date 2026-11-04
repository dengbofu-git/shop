"""Runtime preflight checks schema readiness without changing the database."""
import contextlib
import importlib.util
import io
from pathlib import Path
import types
import unittest
from unittest.mock import MagicMock, Mock, patch


ENTRY = Path(__file__).resolve().parents[1] / 'runtime/backend.py'
spec = importlib.util.spec_from_file_location('runtime_backend_under_test', ENTRY)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class RuntimeBackendPreflightTests(unittest.TestCase):
    def run_entry(self, plans, *, check=True):
        events = []
        connections = {}
        executors = {}
        for alias, plan in plans.items():
            connection = MagicMock()
            connection.cursor.return_value.__enter__.return_value.fetchone.return_value = (1,)
            connection.close.side_effect = lambda alias=alias: events.append(('close', alias))
            connections[alias] = connection
            executor = Mock()
            executor.loader.graph.leaf_nodes.return_value = [('orders', '0009_checkout_group')]
            executor.migration_plan.return_value = plan
            executor.loader.check_consistent_history.side_effect = lambda connection, alias=alias: events.append(('history', alias))
            executors[id(connection)] = executor

        def make_executor(connection):
            events.append(('plan', next(k for k,v in connections.items() if v is connection)))
            return executors[id(connection)]

        command = Mock(side_effect=lambda name, **kwargs: events.append(('command', name)))
        django = types.ModuleType('django')
        django.VERSION = (5, 2)
        django.setup = Mock(side_effect=lambda: events.append(('setup',)))
        management = types.ModuleType('django.core.management')
        management.call_command = command
        executor_module = types.ModuleType('django.db.migrations.executor')
        executor_module.MigrationExecutor = Mock(side_effect=make_executor)
        db = types.ModuleType('django.db')
        db.connections = connections
        dotenv = types.ModuleType('dotenv')
        dotenv.load_dotenv = Mock()
        modules = {'django': django, 'django.core.management': management,
                   'django.db': db, 'django.db.migrations.executor': executor_module, 'dotenv': dotenv}
        stdout = io.StringIO()
        argv = ['backend.py', '--check'] if check else ['backend.py']
        error = None
        with patch.dict('sys.modules', modules), patch.object(backend.sys, 'argv', argv), \
             patch.object(backend.sys, 'version_info', (3, 13)), \
             patch.object(Path, 'is_file', return_value=True), patch.object(backend.os, 'chdir'), \
             patch.dict(backend.os.environ), patch.object(backend.sys, 'path', list(backend.sys.path)), \
             contextlib.redirect_stdout(stdout):
            try:
                backend.main()
            except Exception as exc:
                error = exc
        return error, stdout.getvalue(), command, executors, connections, events

    def test_pending_schema_refuses_preflight_without_running_migrations_or_service(self):
        migration = types.SimpleNamespace(app_label='orders', name='0009_checkout_group')
        error, output, command, executors, connections, events = self.run_entry({'default': [(migration, False)]})
        self.assertIsNotNone(error, 'unapplied schema must fail before preview can stop the old service')
        self.assertIn('orders.0009_checkout_group', str(error))
        self.assertIn('default', str(error))
        self.assertNotIn('passed', output)
        self.assertEqual(command.call_args_list, [unittest.mock.call('check')])
        for executor in executors.values():
            executor.migrate.assert_not_called()
        connections['default'].close.assert_called_once()

    def test_ready_schema_checks_history_and_plan_after_setup_then_closes_every_alias(self):
        error, output, command, executors, connections, events = self.run_entry({'default': [], 'extra': []})
        self.assertIsNone(error)
        self.assertIn('migration readiness passed', output)
        self.assertEqual(events[0:2], [('setup',), ('command', 'check')])
        for alias, connection in connections.items():
            executor = executors[id(connection)]
            executor.loader.check_consistent_history.assert_called_once_with(connection)
            executor.migration_plan.assert_called_once_with([('orders', '0009_checkout_group')])
            executor.migrate.assert_not_called()
            connection.close.assert_called_once()
        self.assertEqual(command.call_args_list, [unittest.mock.call('check')])

    def test_noncheck_mode_keeps_existing_backend_command(self):
        error, output, command, executors, connections, events = self.run_entry({'default': []}, check=False)
        self.assertIsNone(error)
        self.assertEqual(command.call_args.args, ('run_support_backend',))
        self.assertEqual(command.call_args.kwargs, {'addrport': '127.0.0.1:8000', 'mcp_port': 18082, 'mcp_workers': 2})
        self.assertNotIn(('plan', 'default'), events)
