"""Reproduce the existing isolated suite for SDD discovery; no stage approval."""
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import re
import socket
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import TextTestResult
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
PREFIX = sys.argv[1] if len(sys.argv) > 1 else 'baseline'
if not re.fullmatch(r'baseline(?:-[a-z0-9]+)*', PREFIX):
    raise SystemExit('Invalid output prefix')
LABELS = [
    'support_ai.tests', 'support_ai.test_planning',
    'support_ai.test_task_tools', 'support_ai.test_telemetry',
]
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ['DJANGO_SETTINGS_MODULE'] = 'support_ai.test_settings'
os.environ['SUPPORT_API_KEY'] = 'test-model-never-called'
os.environ['SUPPORT_BASE_URL'] = 'https://model.invalid/v1'
os.environ['JWT_SECRET_KEY'] = 'synthetic-sdd-discovery-key-only'


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def snapshot():
    folders = [
        'tea_saas', 'users', 'goods', 'carts', 'orders', 'pays', 'news',
        'inventory', 'logistics', 'supplier', 'admin_panel', 'support_ai',
        'ai_storage', 'client', 'templates',
    ]
    paths = [ROOT / 'manage.py', ROOT / 'requirements.txt', Path(__file__).resolve()]
    for folder in folders:
        paths.extend(p for p in (ROOT / folder).rglob('*')
                     if p.is_file() and p.suffix in {'.py', '.html', '.js', '.css'}
                     and '__pycache__' not in p.parts)
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))}


def git(*args):
    return subprocess.check_output(
        ['git', '-c', 'safe.directory=' + ROOT.as_posix(), *args], cwd=ROOT,
    ).decode('utf-8').strip()


results = []
network_attempts = []


class RecordingResult(TextTestResult):
    def addSuccess(self, test):
        results.append({'id': test.id(), 'result': 'passed'})
        super().addSuccess(test)

    def addFailure(self, test, err):
        results.append({'id': test.id(), 'result': 'failed'})
        super().addFailure(test, err)

    def addError(self, test, err):
        results.append({'id': test.id(), 'result': 'error'})
        super().addError(test, err)

    def addSkip(self, test, reason):
        results.append({'id': test.id(), 'result': 'skipped', 'reason': reason})
        super().addSkip(test, reason)


def no_network(*args, **kwargs):
    network_attempts.append('blocked-socket-connection')
    raise RuntimeError('External network is disabled for SDD discovery')


started = now()
before = snapshot()
head = git('rev-parse', 'HEAD')
branch = git('branch', '--show-current')
log = io.StringIO()
exit_code = 1
with redirect_stdout(log), redirect_stderr(log):
    with patch.object(socket.socket, 'connect', no_network), \
            patch.object(socket.socket, 'connect_ex', no_network), \
            patch.object(socket, 'create_connection', no_network):
        import django
        django.setup()
        from django.conf import settings
        from django.test.runner import DiscoverRunner

        assert all(db['ENGINE'] == 'django.db.backends.sqlite3'
                   and db['NAME'] == ':memory:' for db in settings.DATABASES.values())
        assert all(c['BACKEND'] == 'django.core.cache.backends.locmem.LocMemCache'
                   for c in settings.CACHES.values())
        assert settings.SUPPORT_API_KEY == 'test-model-never-called'

        class RecordingRunner(DiscoverRunner):
            def get_resultclass(self):
                return RecordingResult

        try:
            failures = RecordingRunner(verbosity=2, interactive=False).run_tests(LABELS)
            exit_code = 1 if failures else 0
        finally:
            from support_ai.telemetry import shutdown_telemetry
            shutdown_telemetry()

after = snapshot()
changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
if changed or network_attempts:
    exit_code = 1
log_text = log.getvalue()
(OUT / (PREFIX + '.log')).write_text(log_text, encoding='utf-8')
manifest = {
    'schemaVersion': '0.1', 'evidenceType': 'discovery-baseline',
    'capabilityId': 'CAP-AI-003', 'specVersion': '0.1.0',
    'stagePromotion': False, 'startedAt': started, 'finishedAt': now(),
    'head': head, 'branch': branch, 'workingTree': 'dirty',
    'command': 'E:/miniconda/envs/tea_saas/python.exe docs/sdd/evidence/2026-10-16-ai-003-discovery/run_baseline.py' + (' ' + PREFIX if PREFIX != 'baseline' else ''),
    'python': platform.python_version(), 'django': django.get_version(),
    'environment': {
        'settings': 'support_ai.test_settings',
        'databases': 'SQLite in-memory default + ai_storage',
        'cache': 'LocMem', 'model': 'test doubles; network connections blocked',
        'overrides': ['synthetic SUPPORT_API_KEY', 'model.invalid SUPPORT_BASE_URL', 'synthetic JWT_SECRET_KEY'],
    },
    'exitCode': exit_code, 'testResults': results,
    'blockedNetworkAttempts': len(network_attempts),
    'sourceChangedDuringRun': changed, 'sourceHashes': before,
    'log': PREFIX + '.log',
    'logSha256': hashlib.sha256((OUT / (PREFIX + '.log')).read_bytes()).hexdigest(),
    'logHashAlgorithm': 'sha256-file-bytes',
    'limitations': [
        'Existing regression tests only; no approval of draft acceptance criteria.',
        'No real MySQL/PostgreSQL/Redis, external model or browser verification.',
        'Sequential SQLite tests do not prove production locking or concurrent behavior.',
        'Source hashes cover Python/templates/JS/CSS inputs, not secrets or the whole environment.',
    ],
}
(OUT / (PREFIX + '-manifest.json')).write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({
    'exitCode': exit_code, 'tests': len(results),
    'passed': sum(t['result'] == 'passed' for t in results),
    'blockedNetworkAttempts': len(network_attempts),
    'sourceChangedDuringRun': changed,
    'manifest': str(OUT / (PREFIX + '-manifest.json')),
}, ensure_ascii=False))
raise SystemExit(exit_code)
