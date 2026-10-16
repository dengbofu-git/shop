"""Synthetic, isolated observations of the order-query seam; no model calls."""
import hashlib
import io
import json
import os
from pathlib import Path
import socket
import sys
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
os.environ['DJANGO_SETTINGS_MODULE'] = 'support_ai.test_settings'
os.environ['SUPPORT_API_KEY'] = 'test-model-never-called'
os.environ['SUPPORT_BASE_URL'] = 'https://model.invalid/v1'
os.environ['JWT_SECRET_KEY'] = 'synthetic-sdd-discovery-key-only'
paths = ['support_ai/context.py', 'support_ai/pii.py', 'support_ai/views.py',
         'orders/models.py', 'users/models.py', 'support_ai/models.py',
         'support_ai/test_settings.py', Path(__file__).relative_to(ROOT).as_posix()]
for folder in ['dadashop', 'users', 'goods', 'carts', 'orders', 'pays', 'news',
               'inventory', 'logistics', 'supplier', 'admin_panel', 'support_ai', 'ai_storage']:
    paths.extend(p.relative_to(ROOT).as_posix() for p in (ROOT / folder).rglob('*.py')
                 if '__pycache__' not in p.parts)


def hashes():
    return {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}


before = hashes()
observations = []
network_attempts = []


def no_network(*args, **kwargs):
    network_attempts.append('blocked')
    raise RuntimeError('External network disabled for discovery probes')


def record(id, ac, result, details):
    observations.append({'id': id, 'acceptanceIds': ac, 'result': result, 'details': details})


log = io.StringIO()
with redirect_stdout(log), redirect_stderr(log), \
        patch.object(socket.socket, 'connect', no_network), \
        patch.object(socket.socket, 'connect_ex', no_network), \
        patch.object(socket, 'create_connection', no_network):
    import django
    django.setup()
    from django.conf import settings
    from django.test import Client
    from django.test.runner import DiscoverRunner
    from django.utils import timezone as dj_timezone
    assert all(d['ENGINE'] == 'django.db.backends.sqlite3' and d['NAME'] == ':memory:'
               for d in settings.DATABASES.values())
    runner = DiscoverRunner(verbosity=0, interactive=False)
    runner.setup_test_environment()
    old = runner.setup_databases()
    try:
        from users.models import UserProfile
        from orders.models import OrderInfo, TrialOrder, PreSaleOrder
        from support_ai.models import SupportConversation, SupportTurn
        from support_ai.context import current_order_context
        from support_ai.pii import redact
        from dadashop.utils import jwt_encode
        a = UserProfile.objects.create(username='sdd-a', password='unused', email='a@test.invalid', phone='', is_active=True)
        b = UserProfile.objects.create(username='sdd-b', password='unused', email='b@test.invalid', phone='', is_active=True)

        def order(oid, owner=a, kind='standard', status=1):
            return OrderInfo.objects.create(order_id=oid, user_profile=owner, order_type=kind,
                total_amount='50', total_count=1, freight='0', status=status,
                receiver='合成', address='合成地址', receiver_mobile='13800138000', tag='')

        own = [order('SDD-ORDER-A' + str(i)) for i in range(4)]
        foreign = order('SDD-ORDER-B1', b)
        before_orders = list(OrderInfo.objects.order_by('pk').values())
        safe, dto, selected = current_order_context(a, None, '订单号：' + own[0].pk)
        record('PROBE-AI-003-01', ['AC-AI-003-01', 'AC-AI-003-07'],
               'observed-conforming' if selected == own[0].pk and own[0].pk not in safe + dto else 'gap',
               {'selectedOwnOrder': selected == own[0].pk, 'rows': json.loads(dto), 'safeMessage': safe})
        _, recent, _ = current_order_context(a, None, '最近订单')
        record('PROBE-AI-003-02', ['AC-AI-003-04'],
               'observed-conforming' if len(json.loads(recent)) == 3 else 'gap', {'rowCount': len(json.loads(recent))})

        samples = []
        for oid in [foreign.pk, 'SDD-MISSING-X1']:
            safe, dto, selected = current_order_context(a, None, 'order id: ' + oid)
            samples.append({'syntheticReference': oid, 'safeMessage': safe,
                            'dto': json.loads(dto), 'rawReferenceSurvivesSecondRedaction': oid in redact(safe)})
        record('PROBE-AI-003-03', ['AC-AI-003-03', 'AC-AI-003-07'],
               'gap' if any(s['rawReferenceSurvivesSecondRedaction'] for s in samples) else 'observed-conforming',
               {'samples': samples, 'boundary': 'Application output and workflow redactor; no external model called.'})

        conversation = SupportConversation.objects.create(user=a, active_order_id=own[0].pk, active_order_at=dj_timezone.now())
        own[0].status = 2
        own[0].save(update_fields=['status'])
        _, dto, selected = current_order_context(a, conversation, '那现在呢？')
        fresh = selected == own[0].pk and json.loads(dto)[0]['status'] == '待发货'
        conversation.active_order_at = dj_timezone.now() - timedelta(hours=25)
        _, expired, expired_selected = current_order_context(a, conversation, '那现在呢？')
        record('PROBE-AI-003-04', ['AC-AI-003-05'],
               'observed-conforming' if fresh and not expired_selected else 'gap',
               {'liveStatusReloaded': fresh, 'expiredReferenceSelected': bool(expired_selected), 'expiredRows': len(json.loads(expired))})

        standard = order('SDD-STANDARD', status=4)
        trial = order('SDD-TRIAL', kind='trial', status=None)
        TrialOrder.objects.create(order_info=trial, status=4)
        presale = order('SDD-PRESALE', kind='presale', status=None)
        PreSaleOrder.objects.create(order_info=presale, status=4, deposit_amount='10', balance_amount='40')
        record('PROBE-AI-003-05', ['AC-AI-003-06'], 'observed-conforming', {
            'sameNumericStatus': 4,
            'texts': [standard.get_status_display_text(), trial.get_status_display_text(), presale.get_status_display_text()],
            'boundary': 'One representative state per type; not full state-machine verification.'})

        client = Client()
        cases = []
        for body, auth in [({}, {}), ({}, {'HTTP_AUTHORIZATION': 'Bearer invalid'}),
                           ({'message': '查询订单', 'owner_id': b.pk}, {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': a.pk})})]:
            response = client.post('/v1/support/chat/', data=json.dumps(body), content_type='application/json', **auth)
            cases.append(response.status_code)
        record('PROBE-AI-003-06', ['AC-AI-003-02'],
               'observed-conforming' if cases == [401, 401, 400] else 'gap', {'httpStatuses': cases})
        # Only the intentional state update and new fixture rows may differ above.
        expected = {row['order_id']: row for row in before_orders}
        expected[own[0].pk]['status'] = 2
        after_orders = {row['order_id']: row for row in OrderInfo.objects.filter(pk__in=expected).values()}
        record('PROBE-AI-003-07', ['AC-AI-003-01'],
               'observed-conforming' if expected == after_orders else 'gap',
               {'existingOrderRowsUnchangedByQueries': expected == after_orders,
                'boundary': 'OrderInfo rows at query seam only; not full HTTP or inventory-write verification.'})

        from support_ai.tests import FakeModel
        statuses = []
        turn_counts = []
        raw_model_inputs = []
        for oid in [foreign.pk, 'SDD-MISSING-X1']:
            model = FakeModel({'recommendation': .1, 'question_answering': .1, 'after_sales': .9})
            count_before = SupportTurn.objects.filter(user=a).count()
            with patch('support_ai.model_client.configured_model', return_value=model):
                response = client.post('/v1/support/chat/',
                    data=json.dumps({'message': '查询订单 order id: ' + oid}), content_type='application/json',
                    HTTP_AUTHORIZATION='Bearer ' + jwt_encode({'id': a.pk}))
            statuses.append(response.status_code)
            turn_counts.append(SupportTurn.objects.filter(user=a).count() - count_before)
            raw_model_inputs.append(any(oid in content for _, content in model.calls))
        record('PROBE-AI-003-08', ['AC-AI-003-03'],
               'observed-conforming' if statuses == [404, 404] and turn_counts == [0, 0] and not any(raw_model_inputs) else 'gap',
               {'httpStatuses': statuses, 'newTurnCounts': turn_counts,
               'rawReferencePresentInMockModelInput': raw_model_inputs,
               'boundary': 'Mock-model HTTP probe; current business decision requires uniform 404.'})
    finally:
        runner.teardown_databases(old)
        runner.teardown_test_environment()

after = hashes()
changed = sorted(p for p in before if before[p] != after[p])
manifest = {
    'schemaVersion': '0.1', 'evidenceType': 'discovery-probes',
    'capabilityId': 'CAP-AI-003', 'specVersion': '0.2.0', 'stagePromotion': False,
    'observedAt': datetime.now(timezone(timedelta(hours=8))).isoformat(),
    'command': 'E:/miniconda/envs/dadashop/python.exe docs/sdd/evidence/2026-10-16-ai-003-discovery/run_probes.py',
    'environment': 'support_ai.test_settings; two SQLite memory databases; synthetic data; no model calls',
    'observations': observations, 'blockedNetworkAttempts': len(network_attempts),
    'sourceChangedDuringRun': changed, 'sourceHashes': before,
    'limitations': 'Seam-level observations do not prove model behavior, telemetry privacy, browser behavior, production locking or full AC completion.',
}
(OUT / 'probes-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
(OUT / 'probes.log').write_text(log.getvalue(), encoding='utf-8')
print(json.dumps({'observations': len(observations), 'gaps': [o['id'] for o in observations if o['result'] == 'gap'],
                  'blockedNetworkAttempts': len(network_attempts), 'sourceChangedDuringRun': changed}, ensure_ascii=False))
raise SystemExit(1 if changed or network_attempts else 0)
