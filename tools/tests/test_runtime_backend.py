"""Runtime preflight checks schema readiness without changing the database."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import types
import unittest
from unittest.mock import MagicMock, Mock, patch


ENTRY = Path(__file__).resolve().parents[1] / 'runtime/backend.py'
spec = importlib.util.spec_from_file_location('runtime_backend_under_test', ENTRY)
backend = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend)


class RuntimeBackendPreflightTests(unittest.TestCase):
    def run_entry(self, plans, *, check=True, watch=False, profile_mode=None, enabled=False,
                  vendor='postgresql', ai_alias='default'):
        events = []
        connections = {}
        executors = {}
        for alias, plan in plans.items():
            connection = MagicMock()
            connection.vendor = vendor
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
        conf = types.ModuleType('django.conf')
        conf.settings = types.SimpleNamespace(SUPPORT_AUTO_PROFILE_ENABLED=enabled)
        storage_db = types.ModuleType('ai_storage.database')
        storage_db.alias = Mock(return_value=ai_alias)
        dotenv = types.ModuleType('dotenv')
        dotenv.load_dotenv = Mock()
        modules = {'django': django, 'django.core.management': management, 'django.conf': conf,
                   'django.db': db, 'django.db.migrations.executor': executor_module,
                   'ai_storage.database': storage_db, 'dotenv': dotenv}
        stdout = io.StringIO()
        argv = (['backend.py', '--profile-' + profile_mode] if profile_mode else
                ['backend.py', '--watch-reservations'] if watch else
                ['backend.py', '--check'] if check else ['backend.py'])
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

    def test_profile_status_is_only_safe_boolean_json_without_database_or_command_calls(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled):
                error, output, command, executors, connections, events = self.run_entry(
                    {'default': []}, profile_mode='status', enabled=enabled)
                self.assertIsNone(error)
                self.assertEqual(json.loads(output), {'enabled': enabled})
                command.assert_not_called()
                self.assertNotIn(('plan', 'default'), events)
                connections['default'].cursor.assert_not_called()

    def test_disabled_profile_worker_never_connects_or_starts_a_command(self):
        error, output, command, executors, connections, events = self.run_entry(
            {'default': []}, profile_mode='worker')
        self.assertIn('disabled', str(error))
        self.assertNotIn('TEA_SAAS_PROFILE_WORKER_READY', output)
        command.assert_not_called()
        connections['default'].cursor.assert_not_called()

    def test_enabled_profile_worker_requires_current_schema_before_ready_and_dispatch(self):
        migration = types.SimpleNamespace(app_label='ai_storage', name='0005_auto_profiles')
        error, output, command, executors, connections, events = self.run_entry(
            {'default': [(migration, False)]}, profile_mode='worker', enabled=True)
        self.assertIn('ai_storage.0005_auto_profiles', str(error))
        self.assertNotIn('TEA_SAAS_PROFILE_WORKER_READY', output)
        self.assertEqual(command.call_args_list, [unittest.mock.call('check')])
        for executor in executors.values():
            executor.migrate.assert_not_called()

    def test_ready_profile_worker_dispatches_only_after_unified_postgresql_preflight(self):
        error, output, command, executors, connections, events = self.run_entry(
            {'default': []}, profile_mode='worker', enabled=True)
        self.assertIsNone(error)
        self.assertIn('TEA_SAAS_PROFILE_WORKER_READY', output)
        self.assertEqual(command.call_args_list, [unittest.mock.call('check'), unittest.mock.call('profile_worker')])
        self.assertLess(events.index(('close', 'default')), events.index(('command', 'profile_worker')))

    def test_profile_worker_rejects_split_or_nonpostgres_connections_without_dispatch(self):
        for plans, vendor, alias in (({'default': [], 'extra': []}, 'postgresql', 'default'),
                                     ({'default': []}, 'sqlite', 'default'),
                                     ({'default': []}, 'postgresql', 'extra')):
            with self.subTest(plans=plans, vendor=vendor, alias=alias):
                error, output, command, executors, connections, events = self.run_entry(
                    plans, profile_mode='worker', enabled=True, vendor=vendor, ai_alias=alias)
                self.assertIn('one default PostgreSQL', str(error))
                self.assertNotIn('TEA_SAAS_PROFILE_WORKER_READY', output)
                command.assert_not_called()


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


@unittest.skipUnless(shutil.which('pwsh') or shutil.which('powershell'), 'PowerShell is required for process ownership tests')
class ProfilePreviewOwnershipTests(unittest.TestCase):
    def test_real_functions_reject_foreign_multiple_and_reused_processes_and_disabled_does_not_launch(self):
        preview = str(ENTRY.with_name('preview.ps1')).replace("'", "''")
        scratch = ENTRY.parents[2] / '.scratch'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='runtime-profile-test-', dir=scratch) as directory:
            record_root = directory.replace("'", "''")
            script = r'''
$ErrorActionPreference='Stop'
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('__PREVIEW__', [ref]$null, [ref]$errors)
if ($errors.Count) { throw 'Preview script does not parse' }
$defs = @($ast.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.FunctionDefinitionAst] } | ForEach-Object { $_.Extent.Text }) -join "`n"
. ([scriptblock]::Create($defs))
$entry = 'E:\repo\tools\runtime\backend.py'
$when = [datetime]'2026-11-11T00:00:00Z'
function Row($id, $parent, $line) { [pscustomobject]@{Name='python.exe';ProcessId=$id;ParentProcessId=$parent;CommandLine=$line;CreationDate=$when} }
$one = Row 1 99 'python "E:\repo\tools\runtime\backend.py" --profile-worker'
$two = Row 2 1 'python "E:\repo\tools\runtime\backend.py" --profile-worker'
if (@(Get-ProfileWorkerTree @($one,$two) $entry).Count -ne 2) { throw 'Did not recognize one owned tree' }
foreach ($rows in @(
    ,@($one,(Row 3 99 $one.CommandLine)),
    ,@((Row 4 99 'python "C:\other\tools\runtime\backend.py" --profile-worker')),
    ,@((Row 5 99 'python manage.py profile_worker')),
    ,@((Row 6 99 'python "E:\repo\tools\runtime\backend.py.evil" --profile-worker'))
)) {
    $rejected=$false;try { $null=Get-ProfileWorkerTree $rows $entry } catch { $rejected=$true }
    if (!$rejected) { throw 'Unsafe process source was accepted' }
}
$script:stopCalls=0
function Stop-Process { param($Id,$ErrorAction); $script:stopCalls++ }
function Get-CimInstance { param($ClassName,$Filter)
    [pscustomobject]@{Name='python.exe';ProcessId=1;ParentProcessId=99;CommandLine=$one.CommandLine;CreationDate=$when.AddSeconds(1)}
}
$rejected=$false;try { Stop-VerifiedProfileTree @($one) } catch { $rejected=$true }
if (!$rejected -or $script:stopCalls) { throw 'Reused PID was stopped' }
function Get-CimInstance { param($ClassName,$Filter); return @() }
function Start-Process { throw 'Disabled profile must never launch' }
$result=Sync-ProfileWorker -Enabled $false -Restart $true -ProjectRoot 'E:\repo' -Python 'E:\python.exe' -Entry $entry -BaseArgs @() -RecordRoot '__RECORD__'
if ($result.status -ne 'disabled' -or $result.launcher_pid) { throw 'Disabled profile was not recorded' }
'{"owned_tree":true,"unsafe_sources_rejected":4,"pid_reuse_rejected":true,"disabled_no_launch":true}'
'''.replace('__PREVIEW__', preview).replace('__RECORD__', record_root)
            result = subprocess.run([shutil.which('pwsh') or shutil.which('powershell'), '-NoProfile',
                                     '-NonInteractive', '-Command', script], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.strip()), {
                'owned_tree': True, 'unsafe_sources_rejected': 4, 'pid_reuse_rejected': True, 'disabled_no_launch': True})

    def test_restart_stops_children_then_hidden_start_and_failure_never_claims_readiness(self):
        preview = str(ENTRY.with_name('preview.ps1')).replace("'", "''")
        scratch = ENTRY.parents[2] / '.scratch'
        scratch.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='runtime-profile-test-', dir=scratch) as directory:
            record_root = directory.replace("'", "''")
            script = r'''
$ErrorActionPreference='Stop'
$errors=$null
$ast=[System.Management.Automation.Language.Parser]::ParseFile('__PREVIEW__',[ref]$null,[ref]$errors)
if ($errors.Count) { throw 'Preview script does not parse' }
$defs=@($ast.EndBlock.Statements | Where-Object { $_ -is [System.Management.Automation.Language.FunctionDefinitionAst] } | ForEach-Object { $_.Extent.Text }) -join "`n"
. ([scriptblock]::Create($defs))
$entry='E:\repo\tools\runtime\backend.py';$when=[datetime]'2026-11-11T00:00:00Z'
function Row($id,$parent) { [pscustomobject]@{Name='python.exe';ProcessId=$id;ParentProcessId=$parent;CommandLine='python "E:\repo\tools\runtime\backend.py" --profile-worker';CreationDate=$when} }
$script:liveRows=@((Row 10 99),(Row 11 10));$script:stops=@();$script:starts=0;$script:failStart=$false
function Get-CimInstance { param($ClassName,$Filter)
    if ($Filter) { return @($script:liveRows | Where-Object ProcessId -eq ([int]($Filter -replace '\D',''))) }
    return $script:liveRows
}
function Stop-Process { param($Id,$ErrorAction)
    $script:stops+= $Id;$script:liveRows=@($script:liveRows | Where-Object ProcessId -ne $Id)
}
function Start-Sleep { param($Milliseconds) }
function Start-Process { param($FilePath,$ArgumentList,$WorkingDirectory,$WindowStyle,$RedirectStandardOutput,$RedirectStandardError,[switch]$PassThru)
    if ($WindowStyle -ne 'Hidden' -or $ArgumentList[-1] -ne '--profile-worker') { throw 'Incorrect worker start' }
    $script:starts++
    $id=100+$script:starts
    if ($script:failStart) { $script:liveRows=@() } else {
        $script:liveRows=@((Row $id 99))
        'TEA_SAAS_PROFILE_WORKER_READY' | Set-Content -LiteralPath $RedirectStandardOutput
    }
    $process=[pscustomobject]@{Id=$id;HasExited=$script:failStart}
    $process | Add-Member -MemberType ScriptMethod -Name Refresh -Value {}
    return $process
}
$recordRoot='__RECORD__'
$disabled=Sync-ProfileWorker -Enabled $false -Restart $true -ProjectRoot 'E:\repo' -Python 'E:\python.exe' -Entry $entry -BaseArgs @() -RecordRoot $recordRoot
if (($script:stops -join ',') -ne '11,10' -or $script:starts -or $disabled.status -ne 'disabled') { throw 'Disabled restart did not stop only the verified tree' }
$ready=Sync-ProfileWorker -Enabled $true -Restart $true -ProjectRoot 'E:\repo' -Python 'E:\python.exe' -Entry $entry -BaseArgs @() -RecordRoot $recordRoot
if ($ready.status -ne 'ready' -or $ready.launcher_pid -ne 101 -or !$ready.creation_date -or $script:starts -ne 1) { throw 'Enabled worker did not become ready' }
$script:failStart=$true;$failed=$false
try { $null=Sync-ProfileWorker -Enabled $true -Restart $true -ProjectRoot 'E:\repo' -Python 'E:\python.exe' -Entry $entry -BaseArgs @() -RecordRoot $recordRoot } catch { $failed=$true }
$stored=Get-Content -LiteralPath (Join-Path $recordRoot 'profile-worker.json') -Raw | ConvertFrom-Json
if (!$failed -or $stored.status -ne 'failed' -or !$stored.cleanup_confirmed -or $script:starts -ne 2) { throw 'Failed worker claimed readiness' }
$guard=[IO.File]::Open((Join-Path $recordRoot 'profile-worker.lock'),[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
try {
    $blocked=$false
    try { $null=Sync-ProfileWorker -Enabled $true -Restart $true -ProjectRoot 'E:\repo' -Python 'E:\python.exe' -Entry $entry -BaseArgs @() -RecordRoot $recordRoot } catch { $blocked=$true }
    if (!$blocked -or $script:starts -ne 2) { throw 'Concurrent launcher lock was ignored' }
} finally { $guard.Dispose() }
'{"disabled_restart_stopped_verified_tree":true,"hidden_ready_start":true,"failed_start_rejected":true,"concurrent_launch_blocked":true}'
'''.replace('__PREVIEW__', preview).replace('__RECORD__', record_root)
            result = subprocess.run([shutil.which('pwsh') or shutil.which('powershell'), '-NoProfile',
                                     '-NonInteractive', '-Command', script], capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout.strip()), {
                'disabled_restart_stopped_verified_tree': True, 'hidden_ready_start': True,
                'failed_start_rejected': True, 'concurrent_launch_blocked': True})
