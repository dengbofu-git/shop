"""Read-only source inventory plus isolated regression/probes for SDD reconciliation."""
import ast
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest import TextTestResult
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
APPS = ['users', 'goods', 'carts', 'orders', 'pays', 'news', 'inventory',
        'logistics', 'supplier', 'admin_panel', 'support_ai', 'ai_storage']
LABELS = ['support_ai.tests', 'support_ai.test_planning', 'support_ai.test_task_tools',
          'support_ai.test_telemetry', 'support_ai.test_grouped_recommendations',
          'support_ai.test_mixed_tea', 'ai_storage.tests']
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ['DJANGO_SETTINGS_MODULE'] = 'support_ai.test_settings'
os.environ['SUPPORT_API_KEY'] = 'test-model-never-called'
os.environ['SUPPORT_BASE_URL'] = 'https://model.invalid/v1'
os.environ['JWT_SECRET_KEY'] = 'synthetic-sdd-reconciliation-key-only'


def now():
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def snapshot():
    paths = [ROOT / 'manage.py', ROOT / 'requirements.txt', ROOT / 'versions/modules.json']
    for folder in APPS + ['tea_saas', 'client', 'templates', 'deploy', 'tools']:
        paths.extend(p for p in (ROOT / folder).rglob('*') if p.is_file()
                     and p.suffix in {'.py', '.html', '.js', '.css', '.yml', '.yaml'}
                     and '__pycache__' not in p.parts)
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(set(paths))}


def source_inventory():
    prefixes = {}
    root_tree = ast.parse((ROOT / 'tea_saas/urls.py').read_text(encoding='utf-8'))
    for call in ast.walk(root_tree):
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id == 'path' and len(call.args) >= 2:
            inc = call.args[1]
            if isinstance(inc, ast.Call) and isinstance(inc.func, ast.Name) and inc.func.id == 'include':
                if isinstance(inc.args[0], ast.Constant) and isinstance(call.args[0], ast.Constant):
                    prefixes[inc.args[0].value] = call.args[0].value
    routes, definitions = [], []
    for folder in ['tea_saas'] + APPS:
        urlfile = ROOT / folder / 'urls.py'
        if urlfile.exists():
            tree = ast.parse(urlfile.read_text(encoding='utf-8'))
            for call in ast.walk(tree):
                if (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                        and call.func.id in {'path', 're_path'} and len(call.args) >= 2
                        and isinstance(call.args[0], ast.Constant)):
                    route = str(call.args[0].value)
                    prefix = '' if folder == 'tea_saas' else prefixes.get(folder + '.urls', '')
                    routes.append({'path': '/' + prefix + route, 'view': ast.unparse(call.args[1]),
                                   'source': urlfile.relative_to(ROOT).as_posix(), 'line': call.lineno,
                                   'kind': call.func.id})
        for path in (ROOT / folder).glob('*.py'):
            tree = ast.parse(path.read_text(encoding='utf-8'))
            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    definitions.append({'source': path.relative_to(ROOT).as_posix(), 'line': node.lineno,
                                        'name': node.name, 'decorators': [ast.unparse(d) for d in node.decorator_list],
                                        'methods': [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                                        if isinstance(node, ast.ClassDef) else []})
    return {'routes': routes, 'definitions': definitions}


results, network = [], []


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
    network.append('blocked')
    raise RuntimeError('Network disabled for SDD reconciliation')


started = now()
before = snapshot()
inventory = source_inventory()
head = subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip()
log = io.StringIO()
probes = []
with redirect_stdout(log), redirect_stderr(log), patch.object(socket.socket, 'connect', no_network), \
        patch.object(socket.socket, 'connect_ex', no_network), patch.object(socket, 'create_connection', no_network):
    import django
    django.setup()
    from django.conf import settings
    from django.test import Client
    from django.test.runner import DiscoverRunner
    assert all(d['ENGINE'] == 'django.db.backends.sqlite3' and d['NAME'] == ':memory:' for d in settings.DATABASES.values())
    assert all(c['BACKEND'] == 'django.core.cache.backends.locmem.LocMemCache' for c in settings.CACHES.values())

    class Runner(DiscoverRunner):
        def get_resultclass(self):
            return RecordingResult

    failures = Runner(verbosity=2, interactive=False).run_tests(LABELS)
    from support_ai.telemetry import shutdown_telemetry
    shutdown_telemetry()
    runner = Runner(verbosity=0, interactive=False)
    runner.setup_test_environment()
    old = runner.setup_databases()
    try:
        from users.models import UserProfile
        from orders.models import OrderInfo
        from support_ai.models import SupportConversation, SupportTurn
        from support_ai.context import current_order_context
        from support_ai.tests import FakeModel
        from tea_saas.utils import jwt_encode
        import uuid
        buyer = UserProfile.objects.create(username='audit-buyer', password='unused', email='buyer@test.invalid', phone='', is_active=True)
        other = UserProfile.objects.create(username='audit-other', password='unused', email='other@test.invalid', phone='', is_active=True)
        OrderInfo.objects.create(order_id='SYN-OTHER-001', user_profile=other, total_amount='10', total_count=1,
                                 freight='0', status=1, receiver='合成', address='合成地址', receiver_mobile='', tag='')
        auth = {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': buyer.pk})}
        client = Client()
        response = client.get('/v1/news/list')
        probes.append({'id': 'OBS-NEWS-LOGIN', 'httpStatus': response.status_code,
                       'fact': 'Published news read requires login; not anonymous.'})
        response = client.post('/v1/support/chat/', data='{}', content_type='application/json')
        probes.append({'id': 'OBS-ERROR-SHAPE', 'httpStatus': response.status_code, 'keys': sorted(response.json())})
        for oid in ['SYN-OTHER-001', 'SYN-MISSING-001']:
            message = '查询订单 order id: ' + oid
            safe, dto, selected = current_order_context(buyer, None, message)
            model = FakeModel({'recommendation': .1, 'question_answering': .1, 'after_sales': .9})
            count = SupportTurn.objects.filter(user=buyer).count()
            with patch('support_ai.model_client.configured_model', return_value=model):
                response = client.post('/v1/support/chat/', data=json.dumps({'message': message}), content_type='application/json', **auth)
            probes.append({'id': 'OBS-ORDER-' + ('FOREIGN' if 'OTHER' in oid else 'MISSING'),
                           'httpStatus': response.status_code, 'visibleOrders': json.loads(dto),
                           'rawReferenceInSafeMessage': oid in safe,
                           'rawReferenceInMockModel': any(oid in content for _, content in model.calls),
                           'newSuccessTurns': SupportTurn.objects.filter(user=buyer).count() - count})
        conv = SupportConversation.objects.create(user=buyer, revision=1)
        SupportTurn.objects.create(conversation=conv, user=buyer, sequence=1, request_id=uuid.uuid4(),
                                   request_hash='synthetic', user_text='order id: SYN-OLD-001',
                                   answer='SYN-OLD-001', intent='after_sales', response={'answer': 'SYN-OLD-001'})
        response = client.get('/v1/support/conversations/{}/'.format(conv.pk), **auth)
        probes.append({'id': 'OBS-HISTORY-PROJECTION', 'httpStatus': response.status_code,
                       'rawSyntheticReferenceInBody': 'SYN-OLD-001' in response.content.decode('utf-8')})
    finally:
        shutdown_telemetry()
        runner.teardown_databases(old)
        runner.teardown_test_environment()

after = snapshot()
changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
(OUT / 'source-inventory.json').write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(OUT / 'regression.log').write_text(log.getvalue(), encoding='utf-8')
manifest = {
    'schemaVersion': '0.1', 'evidenceType': 'sdd-reconciliation', 'startedAt': started, 'finishedAt': now(),
    'head': head, 'workingTree': 'dirty', 'scope': '24 capability source reconciliation; runtime tests limited to listed suites/probes',
    'command': 'E:/miniconda/envs/tea_saas/python.exe docs/sdd/evidence/2026-10-16-sdd-reconciliation/run_reconciliation.py',
    'labels': LABELS, 'testResults': results, 'probes': probes,
    'environment': 'SQLite default+ai_storage / LocMem / fake models / blocked sockets',
    'blockedNetworkAttempts': len(network), 'sourceHashes': before, 'sourceChangedDuringRun': changed,
    'implementationVersions': json.loads((ROOT / 'versions/modules.json').read_text(encoding='utf-8'))['modules'],
    'log': 'regression.log', 'logSha256': hashlib.sha256((OUT / 'regression.log').read_bytes()).hexdigest(),
    'stagePromotion': False, 'runtimeAcceptanceComplete': False,
    'limitations': ['Source presence is not full business acceptance.', 'PostgreSQL-only tests may be skipped.',
                    'No real business DB, model, browser, payment, SMS, email or logistics gateway calls.'],
}
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
summary = {status: sum(x['result'] == status for x in results) for status in ['passed', 'failed', 'error', 'skipped']}
summary.update({'tests': len(results), 'probes': len(probes), 'routes': len(inventory['routes']),
                'networkAttempts': len(network), 'sourceChangedDuringRun': changed})
print(json.dumps(summary, ensure_ascii=False))
raise SystemExit(1 if failures or network or changed else 0)
