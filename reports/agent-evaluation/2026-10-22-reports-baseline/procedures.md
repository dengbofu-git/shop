# 本轮探针与执行过程源码

以下保存本轮实际使用的临时脚本，作为测试过程证据，不接入网站或现有评测运行链。实际命令与环境以 checks.json 为准。

复测时使用新的输出批次目录：先将各段代码复制到同名 `.scratch/reports-baseline-20261022/` 文件，修改 capture_baseline、runner 和 probe_reports 的 OUT 为同一个新目录，避免覆盖本批证据。
使用项目 Python 依次运行 capture_baseline.py、run_checks.py、run_checks.py --retry、run_checks.py --currency、run_checks.py --final。当前保存的 runner 已包含工作区 TEMP/TMP 修正，初次权限失败与 RAG 开关覆盖的原始情况见 checks.json 和 verification.md；新复测不应重现已排除的权限问题。
probe_current_contract 导入同目录 probe_reports 的隔离设置。诊断探针中预期的 FileNotFoundError 和旧报告结论用于复现缺陷，不表示这些工具正确。

## capture_baseline.py

SHA256: `b016872a3002d2344c1683311d4cefb32310b3b9c91506040b43426240798398`

```python
import datetime
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports/agent-evaluation/2026-10-22-reports-baseline'
OUT.mkdir(parents=True, exist_ok=True)

def git(*args):
    return subprocess.check_output(['git', *args], cwd=str(ROOT))

paths = sorted(set(git('ls-files', '-c', '-o', '--exclude-standard', '-z').decode('utf-8').split('\0')) - {''})
files = {}
for name in paths:
    if name.startswith(('reports/agent-evaluation/2026-10-22-reports-baseline/',
                        'docs/sdd/evidence/2026-10-22-reports-baseline/')):
        continue
    path = ROOT / name
    if path.is_file():
        payload = path.read_bytes()
        files[name] = {'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
    elif not path.exists():
        files[name] = {'missing': True}

data = {
    'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'baseline': 'Current local working tree, including existing uncommitted changes; not a released or remote-main baseline.',
    'head': git('rev-parse', 'HEAD').decode().strip(),
    'branch': git('branch', '--show-current').decode().strip(),
    'modules': json.loads((ROOT / 'versions/modules.json').read_text(encoding='utf-8')),
    'status': git('status', '--short', '--untracked-files=all').decode('utf-8'),
    'staged_diff_sha256': hashlib.sha256(git('diff', '--cached', '--binary')).hexdigest(),
    'files': files,
}
(OUT / 'baseline.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('Baseline captured: {} paths; HEAD {}'.format(len(files), data['head']))
```

## run_checks.py

SHA256: `62b46fe27142677dcb0cecab6ef090969d749c240ce2d05862b4fd011148080c`

```python
import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports/agent-evaluation/2026-10-22-reports-baseline'
temp_dir = ROOT / '.scratch/reports-baseline-20261022/tmp'
temp_dir.mkdir(parents=True, exist_ok=True)
env = dict(os.environ, PYTHONUTF8='1', DJANGO_SETTINGS_MODULE='support_ai.test_settings',
           LOG_TO_FILE='false', LOG_LEVEL='ERROR', TEMP=str(temp_dir), TMP=str(temp_dir))
checks = [
    ('django-check', [sys.executable, 'manage.py', 'check', '--settings=support_ai.test_settings']),
    ('related-regression', [sys.executable, 'manage.py', 'test', 'support_ai', 'goods.test_images',
                            'goods.test_seed_identity', '--settings=support_ai.test_settings', '--noinput', '-v', '2']),
    ('archive-contract', [sys.executable, 'client/tests/repository-cleanup-contract.py',
                          'RepositoryCleanupTests.test_historical_git_content_is_identical_and_complete',
                          'RepositoryCleanupTests.test_current_comparison_defaults_have_their_historical_inputs', '-v']),
]
if '--retry' in sys.argv:
    checks = [
        ('related-regression-local-temp', [sys.executable, 'manage.py', 'test', 'support_ai', 'goods.test_images',
                                          'goods.test_seed_identity', '--settings=support_ai.test_settings', '--noinput', '-v', '2']),
        ('current-probes', [sys.executable, '.scratch/reports-baseline-20261022/probe_reports.py']),
    ]
if '--currency' in sys.argv:
    checks = [('current-contract', [sys.executable, '.scratch/reports-baseline-20261022/probe_current_contract.py'])]
if '--final' in sys.argv:
    checks = [
        ('final-buyer-shell', [sys.executable, 'manage.py', 'test', 'support_ai.tests.BuyerShellTests',
                               '--settings=support_ai.test_settings', '--noinput', '-v', '2']),
        ('module-ownership', [sys.executable, 'tools/module_versions.py', 'check']),
        ('index-diff-check', ['git', 'diff', '--check', '--', 'reports/README.md', 'reports/agent-evaluation/README.md']),
    ]
previous = json.loads((OUT/'checks.json').read_text(encoding='utf-8')) if any(arg in sys.argv for arg in ('--retry','--currency','--final')) else {}
results = previous.get('results', [])
if results and 'environment' not in results[0]:
    for item in results:
        item['environment'] = {'SUPPORT_RAG_QUERY_ENABLED':'false', 'temporary_directory':'sandbox default (permission failure)'}
for name, command in checks:
    print('START ' + name, flush=True)
    started = time.perf_counter()
    with (OUT / (name + '.log')).open('w', encoding='utf-8') as stream:
        proc = subprocess.run(command, cwd=str(ROOT), env=env, stdout=stream, stderr=subprocess.STDOUT)
    result = {'name': name, 'command': command, 'exit_code': proc.returncode,
              'seconds': round(time.perf_counter() - started, 3), 'log': name + '.log',
              'environment': {'DJANGO_SETTINGS_MODULE':env['DJANGO_SETTINGS_MODULE'], 'TEMP':env['TEMP'],
                              'TMP':env['TMP'], 'LOG_TO_FILE':'false', 'LOG_LEVEL':'ERROR', 'network':'Blocked for custom probes; existing regression uses test doubles'}}
    results.append(result)
    (OUT / 'checks.json').write_text(json.dumps({'executed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                               'settings': 'support_ai.test_settings', 'results': results},
                                              ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('END {} exit={} seconds={}'.format(name, proc.returncode, result['seconds']), flush=True)
```

## probe_reports.py

SHA256: `f891a8deab33dc3696afa6e9f1144751b4eef8ea8a50a97545b7c73f0056e100`

```python
"""Targeted probes; synthetic test data and SQLite only, no network calls."""
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'reports/agent-evaluation/2026-10-22-reports-baseline'
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'support_ai.test_settings'
os.environ['LOG_TO_FILE'] = 'false'
os.environ['LOG_LEVEL'] = 'ERROR'
os.environ['PYTHONUTF8'] = '1'
TEMP = ROOT / '.scratch/reports-baseline-20261022/tmp'
TEMP.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(TEMP)

import django
django.setup()

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.test.runner import DiscoverRunner
from django.urls import resolve
from support_ai.models import SupportConversation, SupportTurn, AgentSpan
from support_ai.preview import PreviewSession, PREVIEW_RUNTIME_VERSION
from users.models import UserProfile
from tea_saas.utils import jwt_encode

observations = {}

def record(name, **data):
    observations[name] = data

class ReportsBaselineProbes(TestCase):
    databases = {'default', 'ai_storage'}

    def test_01_default_preview_directory_is_created_and_text_is_redacted(self):
        with tempfile.TemporaryDirectory() as directory, override_settings(BASE_DIR=Path(directory)), patch(
                'support_ai.preview.configured_model', side_effect=AssertionError('Unexpected model call')):
            expected = Path(directory) / 'reports/agent-preview'
            self.assertFalse(expected.exists())
            session = PreviewSession()
            self.assertTrue(expected.is_dir())
            turn = session.ask('你好')
            session._append({'event': 'synthetic_redaction_probe', 'nested': {'text': '电话13800138000'}})
            text = session.log_path.read_text(encoding='utf-8')
            self.assertNotIn('13800138000', text)
            rows = [json.loads(line) for line in text.splitlines()]
            self.assertEqual([r['event'] for r in rows], ['session_start', 'turn', 'synthetic_redaction_probe'])
            self.assertEqual(turn['model_calls'], 0)
            self.assertEqual(SupportTurn.objects.count(), 0)
            self.assertEqual(SupportConversation.objects.count(), 0)
            self.assertEqual(AgentSpan.objects.count(), 0)
            record('preview_default', directory_suffix='reports/agent-preview', recreated=True,
                   events=[r['event'] for r in rows], redacted=True, customer_turns=0,
                   preview_reported_version=PREVIEW_RUNTIME_VERSION,
                   module_version=json.loads((ROOT/'versions/modules.json').read_text(encoding='utf-8'))['modules']['support_ai']['version'])

    def test_02_cli_creates_a_current_run_log(self):
        output = io.StringIO()
        log_dir = OUT / 'preview-command'
        with patch('support_ai.preview.configured_model', side_effect=AssertionError('Unexpected model call')):
            call_command('agent_preview', message=['你好'], log_dir=str(log_dir), json=True, stdout=output)
        result = json.loads(output.getvalue())
        self.assertEqual(result['event'], 'turn')
        self.assertEqual(result['response']['intents'], ['greeting'])
        self.assertEqual(result['model_calls'], 0)
        self.assertEqual(SupportTurn.objects.count(), 0)
        record('preview_command', response=result, log_directory=log_dir.relative_to(ROOT).as_posix(),
               configuration='Current code and isolated test configuration; no real provider call')

    def test_03_preview_and_http_use_current_product_tools(self):
        from goods.models import Catalog, SPU, SKU
        from support_ai.test_task_tools import ToolModel
        catalog = Catalog.objects.create(name='绿茶')
        spu = SPU.objects.create(name='基线模拟绿茶', catalog=catalog)
        sku = SKU.objects.create(name='50克', caption='', spu=spu, price='40', cost_price='20', market_price='50', stock=10)
        with tempfile.TemporaryDirectory() as directory, patch('support_ai.preview.configured_model', return_value=ToolModel()):
            session = PreviewSession(log_dir=directory)
            preview = session.ask('推荐一款绿茶')['response']
        self.assertEqual([p['sku_id'] for p in preview['recommendations']], [sku.pk])
        self.assertEqual(SupportTurn.objects.count(), 0)
        user = UserProfile.objects.create(username='reports-tools-buyer', is_active=True)
        auth = {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': user.pk})}
        with patch('support_ai.model_client.configured_model', return_value=ToolModel()):
            response = self.client.post('/v1/support/chat/', data=json.dumps({'message': '推荐一款绿茶'}),
                                        content_type='application/json', **auth)
        self.assertEqual(response.status_code, 200)
        http = response.json()
        self.assertEqual([p['sku_id'] for p in http['recommendations']], [sku.pk])
        self.assertEqual(SupportTurn.objects.count(), 1)
        record('preview_http_tools', preview_tasks=preview['tasks'], http_tasks=http['tasks'],
               same_product=True, price=http['recommendations'][0]['price'], currency=http['recommendations'][0]['currency'],
               model='In-process ToolModel test double; not a provider quality evaluation')

    def test_04_http_history_preferences_replay_do_not_use_preview_files(self):
        import uuid
        user = UserProfile.objects.create(username='reports-http-buyer', is_active=True)
        other = UserProfile.objects.create(username='reports-other-buyer', is_active=True)
        auth = {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': user.pk})}
        body = {'message': '你好', 'request_id': str(uuid.uuid4())}
        with patch.object(PreviewSession, '_append', side_effect=AssertionError('HTTP wrote preview log')):
            first = self.client.post('/v1/support/chat/', data=json.dumps(body), content_type='application/json', **auth)
            replay = self.client.post('/v1/support/chat/', data=json.dumps(body), content_type='application/json', **auth)
            self.assertEqual(first.status_code, 200)
            self.assertEqual(replay.json(), first.json())
            self.assertEqual(SupportTurn.objects.count(), 1)
            cid = first.json()['conversation_id']
            listing = self.client.get('/v1/support/conversations/', **auth)
            detail = self.client.get('/v1/support/conversations/' + cid + '/', **auth)
            forbidden = self.client.get('/v1/support/conversations/' + cid + '/',
                HTTP_AUTHORIZATION='Bearer ' + jwt_encode({'id': other.pk}))
            preference_body = {'categories': ['绿茶'], 'brands': [], 'keywords': []}
            put = self.client.put('/v1/support/preferences/', data=json.dumps(preference_body), content_type='application/json', **auth)
            get = self.client.get('/v1/support/preferences/', **auth)
            delete = self.client.delete('/v1/support/preferences/', **auth)
            anonymous = self.client.post('/v1/support/chat/', data='{}', content_type='application/json')
        statuses = {'chat': first.status_code, 'replay': replay.status_code, 'list': listing.status_code,
                    'detail': detail.status_code, 'other_owner': forbidden.status_code,
                    'preference_put': put.status_code, 'preference_get': get.status_code,
                    'preference_delete': delete.status_code, 'anonymous_chat': anonymous.status_code}
        self.assertEqual(statuses, {'chat':200,'replay':200,'list':200,'detail':200,'other_owner':404,
                                   'preference_put':200,'preference_get':200,'preference_delete':200,'anonymous_chat':401})
        record('http_storage', statuses=statuses, stored_turns=1, preview_log_writes=0, preferences=get.json())

    def test_05_url_and_frontend_bindings(self):
        paths = ['/v1/support/chat/', '/v1/support/preferences/', '/v1/support/conversations/',
                 '/v1/support/conversations/00000000-0000-0000-0000-000000000001/',
                 '/v1/goods/index', '/v1/goods/catalogs/1', '/v1/goods/detail/1',
                 '/v1/goods/sku/1/image', '/v1/goods/merchant/sku/1/image']
        bindings = []
        for path in paths:
            matched = resolve(path)
            bindings.append({'path':path,'handler':matched.func.__module__+'.'+matched.func.__name__, 'route':matched.route})
        frontend = (ROOT/'client/static/js/buyer-support.js').read_text(encoding='utf-8')
        for token in ("'/v1/support/'", "api('chat/'", "api('preferences/'", "'/v1/goods/sku/'"):
            self.assertIn(token, frontend)
        record('bindings', routes=bindings, frontend='client/static/js/buyer-support.js',
               coverage='Route resolution plus Django test-client requests; no browser execution')

    def test_06_real_image_manifest_can_be_registered_and_served(self):
        from goods.models import Catalog, SPU, SKU
        manifest_path = ROOT / 'reports/tea-images/2026-10-16/plan.json'
        entries = json.loads(manifest_path.read_text(encoding='utf-8'))['entries']
        skus = []
        for entry in entries:
            target = Path(settings.MEDIA_ROOT) / entry['file']
            self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), entry['sha256'])
            catalog = Catalog.objects.create(name=entry['name'])
            spu = SPU.objects.create(name='基线模拟'+entry['name'], catalog=catalog)
            skus.append(SKU.objects.create(spu=spu, name='模拟规格', caption='', price=10, cost_price=5, market_price=12, stock=10))
        output = io.StringIO()
        call_command('register_tea_images', manifest=str(manifest_path), stdout=output)
        self.assertEqual(Catalog.objects.exclude(fallback_image='').count(), 0)
        for _ in range(2):
            call_command('register_tea_images', manifest=str(manifest_path), apply=True, stdout=output)
        statuses = []
        for sku, entry in zip(skus, entries):
            response = self.client.get('/v1/goods/sku/{}/image'.format(sku.pk))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['X-Image-Source'], 'catalog-virtual')
            self.assertEqual(hashlib.sha256(response.content).hexdigest(), entry['sha256'])
            sku.refresh_from_db()
            self.assertFalse(sku.default_image_url)
            statuses.append({'category':entry['name'],'status':response.status_code,'source':response['X-Image-Source']})
        record('image_manifest', registered=len(entries), hash_checks=len(entries), served=statuses,
               idempotent=True, media_files='Read only; apply affected isolated SQLite catalogs only')

    def test_07_historical_report_dependency_and_stale_replay_path(self):
        from support_ai.evaluation import report, replay_grouped_preview
        archive = ROOT / 'reports/archive/2026-10-16/agent-evaluation/2026-10-16-planner'
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            for name in ('paired-final.json','cases.json'):
                shutil.copyfile(str(archive/name), str(directory/name))
            with patch.object(report, 'ROOT', directory), patch('sys.stdout', new=io.StringIO()):
                report.main()
            self.assertTrue((directory/'summary.json').exists())
            self.assertTrue((directory/'comparison-report.md').exists())
            with patch.object(sys,'argv',['replay_grouped_preview','--output',str(directory/'replay.json')]):
                with self.assertRaises(FileNotFoundError):
                    replay_grouped_preview.main()
        old = 'reports/agent-evaluation/2026-10-16-grouping/before/20261016-114613-cf6a9b60bb8047dead1a4663ec911451.jsonl'
        archived = old.replace('reports/agent-evaluation/', 'reports/archive/2026-10-16/agent-evaluation/')
        self.assertFalse((ROOT/old).exists())
        self.assertTrue((ROOT/archived).exists())
        record('historical_tools', report_input=str(report.ROOT), report_outputs_generated_in_temporary_copy=True,
               stale_replay_missing=old, archived_input_exists=archived,
               replay_result='FileNotFoundError before model invocation; current defect reproduced')

    def test_08_scenario_reporter_reuses_fixed_historical_judgments(self):
        from support_ai.evaluation import report_scenario_suite
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            cases = [{'id':i,'session':'synthetic','message':'SYNTHETIC INPUT '+str(i),'expected_intents':[['greeting']]} for i in range(1,16)]
            rows = [{'case_id':i,'elapsed_seconds':0.001,'model_calls':0,'input_tokens':0,'output_tokens':0,'context_turns':0,
                     'response':{'intents':['greeting'],'answer':'SYNTHETIC SUCCESS','recommendations':[]},
                     'checks':{'intent_sequence':True,'catalog_identity_and_price':True},'audit':{'tool_results':[]}} for i in range(1,16)]
            (directory/'manifest.json').write_text(json.dumps({'cases':cases}), encoding='utf-8')
            (directory/'run-summary.json').write_text(json.dumps({'exact_intent_matches':15,'model_calls':0,'input_tokens':0,'output_tokens':0}),encoding='utf-8')
            (directory/'results.jsonl').write_text('\n'.join(json.dumps(r) for r in rows),encoding='utf-8')
            with patch.object(sys,'argv',['report_scenario_suite',str(directory)]), patch('sys.stdout',new=io.StringIO()):
                report_scenario_suite.main()
            review = json.loads((directory/'review.json').read_text(encoding='utf-8'))
            content = (directory/'report.md').read_text(encoding='utf-8')
            self.assertIn('0.8.1', content)
            self.assertIn('2026-10-16', content)
            self.assertEqual(review['metrics']['review_status_counts']['失败'], 6)
            record('scenario_reporter', synthetic_automatic_passes=15, reused_manual_statuses=review['metrics']['review_status_counts'],
                   reused_version='0.8.1', reused_date='2026-10-16',
                   verdict='Historical formatter, unsuitable as a current generic report generator',
                   synthetic_outputs_kept=False)

    def test_09_virtual_product_command_requires_mysql_before_writes(self):
        from datetime import date
        from goods.management.commands.seed_virtual_tea_products import build_products
        from goods.models import SKU
        products = build_products('BASELINE20261022', date(2026,10,22))
        self.assertEqual(len(products), 100)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'uncreated'
            with self.assertRaisesMessage(CommandError,'requires the business MySQL'):
                call_command('seed_virtual_tea_products', merchant_id=1, expected_database_name='synthetic-only',
                             expected_server_uuid='synthetic-only', batch='BASELINE20261022', as_of='2026-10-22', report_dir=str(target))
            self.assertFalse(target.exists())
        self.assertEqual(SKU.objects.count(), 0)
        record('virtual_products', planned_products=len(products), sqlite_write_guard='rejected before directory or row creation',
               mysql_end_to_end='Not executed; no business database writes')

if __name__ == '__main__':
    with patch('socket.socket.connect', side_effect=AssertionError('Network is disabled for baseline probes')):
        failures = DiscoverRunner(verbosity=2, interactive=False).run_tests(['__main__.ReportsBaselineProbes'])
    (OUT/'probe-observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf-8')
    sys.exit(bool(failures))
```

## probe_current_contract.py

SHA256: `b9c79faa1194c7bf7e6022e892f5d5c3ba1988e7f9c4e31222074dead7b4e11b`

```python
"""Check the four failing legacy expectations against current currency/task rules."""
import json
from unittest.mock import patch
import probe_reports as baseline
from django.test.runner import DiscoverRunner
from support_ai.test_grouped_recommendations import GroupedRecommendationTests
from support_ai.test_mixed_tea import MixedTeaIntegrationTests
from support_ai.tests import RecommendationIntegrationTests
from support_ai.test_semantic_planning import SemanticPlanningTests, PlanModel
from support_ai.semantic_planning import plan_turn, response_state
from support_ai.contracts import RecommendationIntent
from support_ai.recommendations import match_products

observations = {}

class CurrentGrouping(GroupedRecommendationTests):
    def test_current_contract(self):
        message = '按不同茶类推荐，每盒不超过12美元，不要红茶'
        def evidence(field,value):
            return {'field':field,'value':value,'source':'CURRENT','quote':message}
        payload = {'action':'SEARCH','required':{'price_max':'12','currency':'USD','price_basis':'unit'},
                   'excluded':{'categories':['红茶']},'evidence':[evidence('required.price_max','12'),
                    evidence('required.currency','USD'),evidence('required.price_basis','unit'),evidence('excluded.categories','红茶')]}
        result = self.run_tool(message,payload)
        cards = result.data['recommendations']
        self.assertEqual([p['category'] for p in cards], ['绿茶','白茶','乌龙茶','黄茶','黑茶'])
        self.assertTrue(all(p['currency']=='CNY' and float(p['price'])<=85.71 for p in cards))
        observations['grouped_budget'] = {'input_usd':12,'current_cny_upper_bound':'85.71',
            'returned_categories':[p['category'] for p in cards], 'red_excluded':True}

class CurrentMixed(MixedTeaIntegrationTests):
    def test_current_contract(self):
        data = self.run_graph('说明绿茶和红茶的区别，并推荐对应商品，每盒不超过10美元')['response']
        self.assertEqual([p['category'] for p in data['recommendations']], ['绿茶','红茶'])
        self.assertTrue(all(p['currency']=='CNY' and float(p['price'])<=71.42 for p in data['recommendations']))
        self.assertEqual(data['product_intent']['required']['price_max'],'10.00')
        self.assertEqual(data['product_intent']['required']['currency'],'USD')
        observations['mixed_budget'] = {'input_usd':10,'current_cny_upper_bound':'71.42',
            'returned_categories':[p['category'] for p in data['recommendations']], 'original_budget_preserved':True}

class CurrentMatching(RecommendationIntegrationTests):
    def test_current_contract(self):
        intent = RecommendationIntent(action='SEARCH',required={'categories':['绿茶'],'price_max':'50','currency':'USD','price_basis':'unit'})
        foreign = match_products(intent)
        self.assertEqual([p['sku_id'] for p in foreign['recommendations']], [self.skus[1].pk,self.skus[2].pk])
        intent.required.currency = 'CNY'
        base = match_products(intent)
        self.assertEqual([p['sku_id'] for p in base['recommendations']], [self.skus[1].pk])
        intent.required.price_max = '10.00'
        self.assertEqual(match_products(intent)['recommendation_status'],'NO_MATCH')
        observations['matching_budget'] = {'usd_50_returns_cny_prices':[p['price'] for p in foreign['recommendations']],
            'cny_50_returns_cny_prices':[p['price'] for p in base['recommendations']],
            'cny_10':'NO_MATCH', 'hidden_and_exhausted_products_excluded':True}

class CurrentSemantic(SemanticPlanningTests):
    def test_current_contract(self):
        model = PlanModel({'action':'not-used'})
        plan, source, previous = plan_turn(model,'美元',self.history(),None)
        self.assertEqual(source,'rules')
        self.assertEqual(model.calls,[])
        self.assertEqual(plan.purchase.required.categories,['绿茶'])
        self.assertEqual(plan.purchase.required.price_max,'50.00')
        self.assertEqual(plan.purchase.required.currency,'USD')
        self.assertEqual(plan.purchase.required.price_basis,'unit')
        saved = response_state(plan,{},previous)
        self.assertEqual(saved['limit'],2)
        self.assertEqual(saved['status'],'completed')
        observations['currency_supplement'] = {'source':source,'model_calls':len(model.calls),
            'conditions':plan.purchase.model_dump(mode='json'),'count_preserved':saved['limit']}

if __name__ == '__main__':
    labels = ['__main__.'+name+'.test_current_contract' for name in
              ('CurrentGrouping','CurrentMixed','CurrentMatching','CurrentSemantic')]
    with patch('socket.socket.connect',side_effect=AssertionError('Network is disabled for baseline probes')):
        failures = DiscoverRunner(verbosity=2,interactive=False).run_tests(labels)
    (baseline.OUT/'current-contract-observations.json').write_text(json.dumps(observations,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    raise SystemExit(bool(failures))
```
