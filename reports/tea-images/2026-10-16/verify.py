"""Narrow image and buyer-activity regression evidence; no business data writes."""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
os.chdir(ROOT)
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
os.environ['PYTHONIOENCODING'] = 'utf-8'
paths = ['goods/models.py', 'goods/images.py', 'goods/views.py', 'goods/merchant_views.py',
         'goods/migrations/0010_catalog_fallback_image.py', 'goods/test_images.py',
         'goods/test_activity.py', 'goods/management/commands/register_tea_images.py',
         'carts/views.py', 'orders/views.py', 'versions/modules.json',
         'docs/sdd/modules/catalog-content/image-fallback.md']


def snapshot():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


def run(name, args):
    result = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, cwd=ROOT)
    (OUT / (name + '.log')).write_bytes(result.stdout)
    print(f'{name}: exit {result.returncode}', flush=True)
    return {'command': args, 'exitCode': result.returncode, 'log': name + '.log'}


before = snapshot()
results = [
    run('sqlite', [sys.executable, 'manage.py', 'test', 'goods.test_images', 'goods.test_activity',
                   '--settings=support_ai.test_settings', '--noinput', '-v', '2']),
    run('mysql', [sys.executable, 'manage.py', 'test', 'goods.test_images', 'goods.test_activity',
                  '--settings=goods.test_mysql_settings', '--noinput', '-v', '2']),
    run('migration-drift', [sys.executable, 'manage.py', 'makemigrations', 'goods', '--check',
                            '--dry-run', '--settings=support_ai.test_settings']),
    run('versions', [sys.executable, 'tools/module_versions.py', 'check']),
]
after = snapshot()
audit = json.loads((OUT / 'database-audit.json').read_text(encoding='utf-8'))
plan = json.loads((OUT / 'plan.json').read_text(encoding='utf-8'))
for entry in plan['entries']:
    assert hashlib.sha256((ROOT / 'media' / entry['file']).read_bytes()).hexdigest() == entry['sha256']
head = subprocess.check_output(['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'rev-parse', 'HEAD'], text=True).strip()
report = {
    'type': 'verification', 'capability': 'CAP-CAT-001 / FEAT-004 image fallback increment',
    'time': datetime.now(timezone(timedelta(hours=8))).isoformat(),
    'head': head, 'workingTreeDirty': True, 'inputHashes': after, 'inputsStable': before == after,
    'commands': results, 'generator': 'built-in image_gen', 'promptSet': 'plan.json',
    'assets': [{'name': e['name'], 'file': e['file'], 'sha256': e['sha256']} for e in plan['entries']],
    'localDatabaseAudit': {'file': 'database-audit.json', 'skuCount': audit['skuCount'], 'counts': audit['counts'],
                           'realUploadsUnchanged': audit['realUploadsUnchanged']},
    'localDeployment': {'migration': 'goods.0010_catalog_fallback_image', 'result': 'applied',
                        'registrationCommand': 'manage.py register_tea_images --manifest reports/tea-images/2026-10-16/plan.json --apply',
                        'registeredCatalogs': 6},
    'limitations': ['No production release, full-site regression or browser acceptance.',
                    'Cart test uses fake Redis; no transaction or price semantics changed.'],
    'reviewer': None,
}
report['result'] = 'pass' if before == after and all(r['exitCode'] == 0 for r in results) else 'fail'
(OUT / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('result: ' + report['result'], flush=True)
sys.exit(0 if report['result'] == 'pass' else 1)
