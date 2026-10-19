"""Capture commands, logs and working-tree hashes for this capability only."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'


def run(name, args):
    result = subprocess.run(args, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (OUT / (name + '.log')).write_bytes(result.stdout)
    print(name + ': exit ' + str(result.returncode), flush=True)
    return {'command': args, 'exitCode': result.returncode, 'log': name + '.log'}


paths = [
    'goods/models.py', 'goods/activity_views.py', 'goods/views.py', 'goods/urls.py',
    'goods/migrations/0009_browsinghistory_favorite.py', 'goods/test_activity.py',
    'goods/test_mysql_settings.py', 'support_ai/test_settings.py', 'tea_saas/urls.py',
    'client/templates/buyer_header.html', 'client/templates/buyer_activity.html',
    'client/templates/product_details.html', 'client/static/js/buyer-activity.js',
    'client/static/css/buyer-activity.css', 'versions/modules.json',
]


def hashes():
    return {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}


before = hashes()
commands = [run('sqlite', [sys.executable, 'manage.py', 'test', 'goods.test_activity',
                          '--settings=support_ai.test_settings', '--noinput', '-v', '2']),
            run('mysql', [sys.executable, 'manage.py', 'test', 'goods.test_activity',
                         '--settings=goods.test_mysql_settings', '--noinput', '-v', '2']),
            run('migration-drift', [sys.executable, 'manage.py', 'makemigrations', 'goods',
                                   '--check', '--dry-run', '--settings=support_ai.test_settings']),
            run('js-syntax', ['node', '--check', 'client/static/js/buyer-activity.js']),
            run('versions', [sys.executable, 'tools/module_versions.py', 'check']),
            run('sdd-consistency', [sys.executable, str(OUT / 'check_spec.py')])]
after = hashes()
head = subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'rev-parse', 'HEAD'], text=True).strip()
manifest = {
    'type': 'verification', 'capabilityId': 'CAP-CAT-004', 'specVersion': '0.1.0',
    'time': datetime.now(timezone(timedelta(hours=8))).isoformat(),
    'head': head, 'workingTreeDirty': True, 'inputHashes': after, 'inputsStable': before == after,
    'implementationVersions': {k: v['version'] for k, v in json.loads(
        (ROOT / 'versions/modules.json').read_text(encoding='utf-8'))['modules'].items()
        if k in ('goods', 'web', 'core')},
    'introducedVersions': {'goods': '0.3.0', 'web': '0.5.0', 'core': '0.1.4'},
    'environment': {'python': sys.version, 'databases': ['SQLite in-memory', 'MySQL unique disposable test database'],
                    'cache': 'LocMem', 'externalModels': 'not-called'},
    'commands': commands, 'acceptanceIds': ['AC-CAT-004-%02d' % i for i in range(1, 10)],
    'browser': {'environment': 'temporary SQLite, synthetic data, localhost:8001',
                'checks': ['navigation-pagination', 'detail-favorite', 'detail-recent', 'clear-empty', 'language-rtl'],
                'screenshots': ['favorites.png', 'recent.png'],
                'mobile': 'single column; clientWidth=scrollWidth=375; viewport restored'},
    'deploymentObservation': {'environment': 'configured local default MySQL',
                              'command': 'manage.py migrate goods 0009 --database default --noinput',
                              'result': 'goods.0009_browsinghistory_favorite applied successfully',
                              'note': 'Migration only; no production release approval.'},
    'reviewer': None,
    'limitations': ['Browser network failure and authorization error-state probes not executed.',
                    'No production release or full-site regression; existing unrelated dirty changes preserved.'],
}
manifest['result'] = 'pass' if before == after and all(c['exitCode'] == 0 for c in commands) else 'fail'
(OUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('result: ' + manifest['result'], flush=True)
sys.exit(0 if manifest['result'] == 'pass' else 1)
