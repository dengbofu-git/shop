"""Run preregistered synthetic multi-turn dialogues through the actual public Agent.

No provider outputs are mocked. The graph wrapper only copies returned state.
Customer history, configuration, catalog and telemetry are read-only.
"""
import argparse
from contextlib import ExitStack
from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import re
import statistics
from types import SimpleNamespace
from unittest.mock import patch


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding='utf-8')


def score(spec, record, prior):
    response = record.get('response', {})
    cards = response.get('recommendations', [])
    explained = response.get('explained_products', [])
    checks = []
    def check(name, passed, actual=None):
        checks.append({'check':name, 'passed':bool(passed), 'actual':actual})
    check('returned_turn', record.get('event') == 'turn', record.get('error_type'))
    check('not_compliance_blocked', not response.get('compliance_blocked', False))
    if 'intents' in spec:
        check('ordered_intents', response.get('intents') == spec['intents'], response.get('intents'))
    check('clarification_expected', bool(response.get('clarification_required')) == bool(spec.get('clarify')),
          response.get('clarification_required'))
    if 'categories' in spec:
        check('product_categories', bool(cards) and {p['category'] for p in cards} == set(spec['categories']),
              [p['category'] for p in cards])
    if 'count' in spec:
        check('requested_product_count', len(cards) == spec['count'], len(cards))
    if spec.get('no_cards'):
        check('no_products_on_clarification', not cards and not explained)
    if 'groups' in spec:
        groups = [g['category'] for g in response.get('recommendation_groups', [])]
        check('category_groups', groups == spec['groups'], groups)
    if spec.get('grouped'):
        check('grouped_mode', response.get('recommendation_options', {}).get('mode') == 'by_category')
    intent = response.get('product_intent', {})
    if spec.get('required_categories_empty'):
        check('reset_category_filter', not intent.get('required', {}).get('categories'), intent.get('required', {}).get('categories'))
    if spec.get('topic'):
        check('grounded_topic_inheritance', bool(response.get('topic_inheritance')), response.get('topic_inheritance'))
    if 'exclude_categories' in spec:
        excluded = set(spec['exclude_categories'])
        check('excluded_categories_absent', bool(cards) and not any(p['category'] in excluded for p in cards))
        check('excluded_contract', excluded <= set(intent.get('excluded', {}).get('categories', [])))
    if 'price_max' in spec:
        maximum = Decimal(spec['price_max'])
        check('live_prices_within_budget', bool(cards) and all(Decimal(p['price']) <= maximum for p in cards))
        check('budget_limit_retained', intent.get('required', {}).get('price_max') == spec['price_max'], intent.get('required', {}))
    if spec.get('budget_contract'):
        required = intent.get('required', {})
        check('budget_currency_basis', required.get('currency') == 'USD' and required.get('price_basis') == 'unit')
    if 'calls_max' in spec:
        check('bounded_model_calls', record.get('model_calls', 999) <= spec['calls_max'], record.get('model_calls'))
    if 'explain_from' in spec:
        original = prior.get(spec['explain_from'], {}).get('response', {}).get('recommendations', [])
        if 'positions' in spec:
            original = [original[p-1] for p in spec['positions'] if 0 < p <= len(original)]
        expected = [c['sku_id'] for c in original]
        actual = [c['sku_id'] for c in explained]
        check('same_bound_product_ids', bool(expected) and actual == expected, {'expected':expected,'actual':actual})
        if spec.get('intents') == ['recommendation_explanation']:
            check('no_new_recommendations', not cards)
        check('reason_contains_grounded_facts', '推荐依据' in response.get('answer', '') and bool(explained))
    if spec.get('reason_answer'):
        check('same_turn_reason_text', '推荐依据' in response.get('answer', ''))
    if spec.get('knowledge'):
        tools = record.get('audit', {}).get('tool_results', [])
        check('knowledge_has_evidence', any(t['tool'] == 'introduce_tea' and t['status'] == 'success'
              and (t['data'].get('evidence') or t['data'].get('explained_categories')) for t in tools))
    return {'passed':all(c['passed'] for c in checks), 'checks':checks}


def contract_probes():
    from pydantic import ValidationError
    from support_ai.contracts import RecommendationIntent, validate_recommendation_intent
    base = {'action':'SEARCH','required':{'categories':['白茶']}, 'evidence':[
        {'field':'required.categories','value':'白茶','source':'CURRENT','quote':'白茶'}]}
    rows = []
    def probe(name, raw, message='推荐白茶', reject=True):
        try:
            validate_recommendation_intent(RecommendationIntent.model_validate(raw), message, [], None)
            rejected = False
        except (ValidationError, ValueError):
            rejected = True
        rows.append({'name':name,'expected_reject':reject,'rejected':rejected,'passed':rejected == reject})
    probe('合法原话分类', base, reject=False)
    for field in ('required.categories[0]', 'required.categories.0', 'quantity', 'reasons', 'limit'):
        raw = json.loads(json.dumps(base))
        raw['evidence'][0]['field'] = field
        probe('拒绝非法字段 ' + field, raw)
    raw = json.loads(json.dumps(base)); raw['evidence'][0]['quote'] = '绿茶'
    probe('拒绝不匹配原话证据', raw)
    raw = json.loads(json.dumps(base)); raw['evidence'][0].update(source='CONTEXT',source_id='turn-foreign')
    probe('拒绝不存在历史轮次', raw)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    root = Path(args.output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if any((root/name).exists() for name in ('manifest.json','results.jsonl','summary.json')):
        raise RuntimeError('Choose a fresh directory; existing results are preserved')
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','tea_saas.settings')
    import django
    django.setup()
    from django.db import connections
    from django.utils import timezone
    from support_ai import preview
    from support_ai.configuration import effective_configuration
    from support_ai.models import SupportConversation, SupportTurn, AgentSpan
    from support_ai.recommendations import available_products, product_cards
    from support_ai.query_rewrite import QueryPolicy

    def readonly(execute, sql, params, many, context):
        if re.match(r'\s*(INSERT|UPDATE|DELETE|REPLACE|CREATE|ALTER|DROP|TRUNCATE)\b', sql, re.I):
            raise RuntimeError('Evaluation prohibits database mutations')
        return execute(sql, params, many, context)

    cases_path = Path(__file__).with_name('dialogue_followup_cases.json')
    cases = json.loads(cases_path.read_text(encoding='utf-8'))
    if len(cases) != 15:
        raise RuntimeError('Expected exactly 15 independent dialogues')
    files = ['support_ai/'+name for name in ('conversation_tasks.py','recommendation_explanations.py',
        'tool_services.py','contracts.py','context.py','planning.py','workflow.py','recommendations.py',
        'preview.py','retrieval.py','query_rewrite.py','configuration.py','model_client.py')]
    hashes = {name:digest(name) for name in files}
    with ExitStack() as stack:
        for connection in connections.all():
            stack.enter_context(connection.execute_wrapper(readonly))
        config = replace(effective_configuration(),telemetry_enabled=False,export_enabled=False)
        class FrozenSession(preview.PreviewSession):
            def configuration(self):
                return config
        counts = lambda:{'turns':SupportTurn.objects.count(),'conversations':SupportConversation.objects.count(),
                          'spans':AgentSpan.objects.count()}
        before_counts = counts()
        catalog = product_cards(list(available_products().order_by('id')))
        dump(root/'catalog-before.json',catalog)
        dump(root/'cases.json',cases)
        probes = contract_probes()
        dump(root/'contract-probes.json',probes)
        manifest = {'started_at':timezone.now().isoformat(),'runtime':preview.PREVIEW_RUNTIME_VERSION,
            'configuration':asdict(config),'query_policy':asdict(QueryPolicy.current()),
            'dialogues':len(cases),'turns':sum(len(c['turns']) for c in cases),
            'scope':'synthetic public conversations; real model/catalog/RAG; fresh independent sessions',
            'method':'sequential, one sample per input, frozen model configuration, no business/telemetry writes',
            'source_sha256':hashes,'case_sha256':digest(cases_path),'business_counts_before':before_counts,
            'limits':'Structural assertions and manual answer review; not a population accuracy estimate. No baseline arm.'}
        dump(root/'manifest.json',manifest)
        original_build = preview.build_graph
        captured = {}
        def observe_graph(*a, **kw):
            graph = original_build(*a, **kw)
            def invoke(*ia, **ikw):
                state = graph.invoke(*ia, **ikw)
                captured['state'] = preview.safe_record({k:state.get(k) for k in
                    ('resolved_question','plan','tool_results','compliance_blocked')})
                return state
            return SimpleNamespace(invoke=invoke)
        records = []
        with patch('support_ai.preview.build_graph', side_effect=observe_graph):
            for case in cases:
                session = FrozenSession(log_dir=root/'sessions'/str(case['id']).zfill(2))
                prior = {}
                for index, turn in enumerate(case['turns'],1):
                    captured.clear()
                    print(json.dumps({'event':'start','case':case['id'],'turn':index,'message':turn['message']},ensure_ascii=False),flush=True)
                    try:
                        record = session.ask(turn['message'])
                    except Exception as exc:
                        record = session.last_error or {'event':'error','error_type':type(exc).__name__}
                    record = preview.safe_record(dict(record,case_id=case['id'],turn_index=index,scene=case['scene'],
                        expected=turn['expect'],audit=captured.get('state',{})))
                    record['evaluation'] = score(turn['expect'],record,prior)
                    prior[index] = record
                    records.append(record)
                    with (root/'results.jsonl').open('a',encoding='utf-8') as stream:
                        stream.write(json.dumps(record,ensure_ascii=False,default=str)+'\n')
                    print(json.dumps({'event':'done','case':case['id'],'turn':index,
                        'passed':record['evaluation']['passed'],'intents':record.get('response',{}).get('intents'),
                        'calls':record.get('model_calls'),'seconds':record.get('elapsed_seconds'),
                        'failed_checks':[c['check'] for c in record['evaluation']['checks'] if not c['passed']],
                        'answer':record.get('response',{}).get('answer','')[:100]},ensure_ascii=False),flush=True)
        after_catalog = product_cards(list(available_products().order_by('id')))
        dump(root/'catalog-after.json',after_catalog)
        after_counts = counts()
        summary = {'completed_at':timezone.now().isoformat(),'dialogues':len(cases),'turns':len(records),
            'returned_turns':sum(r.get('event') == 'turn' for r in records),
            'turn_assertions_passed':sum(r['evaluation']['passed'] for r in records),
            'dialogues_all_assertions_passed':sum(all(r['evaluation']['passed'] for r in records if r['case_id']==c['id']) for c in cases),
            'model_calls':sum(r.get('model_calls',0) for r in records),
            'input_tokens':sum(r.get('input_tokens',0) for r in records),
            'output_tokens':sum(r.get('output_tokens',0) for r in records),
            'mean_seconds':statistics.mean(r.get('elapsed_seconds',0) for r in records),
            'median_seconds':statistics.median(r.get('elapsed_seconds',0) for r in records),
            'sum_turn_seconds':sum(r.get('elapsed_seconds',0) for r in records),
            'source_unchanged':hashes == {name:digest(name) for name in files},
            'catalog_unchanged':catalog == after_catalog,
            'business_counts_before':before_counts,'business_counts_after':after_counts,
            'business_counts_unchanged':before_counts == after_counts,
            'contract_probes_passed':sum(p['passed'] for p in probes),'contract_probes_total':len(probes),
            'cases':[{'id':c['id'],'scene':c['scene'],'passed':all(r['evaluation']['passed'] for r in records if r['case_id']==c['id']),
                'failed_turns':[r['turn_index'] for r in records if r['case_id']==c['id'] and not r['evaluation']['passed']]} for c in cases]}
        dump(root/'summary.json',summary)
        print(json.dumps({'event':'complete',**summary},ensure_ascii=False),flush=True)
        lines = ['# 15 组模拟场景的真实 Agent 对话记录','',
            '版本：{}；模型：{}；配置修订：{}。共 {} 轮。'.format(preview.PREVIEW_RUNTIME_VERSION,config.model,config.revision,len(records)),
            '','下列为真实返回，包含失败和澄清；断言结果仅评价预定义行为，不等于知识事实正确率。','']
        for case in cases:
            lines += ['## {}. {}'.format(case['id'],case['scene']),'']
            for r in records:
                if r['case_id'] != case['id']:
                    continue
                lines += ['### 第 {} 轮'.format(r['turn_index']),'','**用户：** '+r.get('message',''),'','**Agent：**',
                    '',r.get('response',{}).get('answer','本轮失败：'+str(r.get('error_type'))),'',
                    '意图：`{}`；耗时：{}s；模型调用：{}；预定义断言：{}。'.format(
                        ' → '.join(r.get('response',{}).get('intents',[])),r.get('elapsed_seconds'),r.get('model_calls'),
                        '通过' if r['evaluation']['passed'] else '未通过'),'']
                failures = [c for c in r['evaluation']['checks'] if not c['passed']]
                if failures:
                    lines += ['未通过项：`'+json.dumps(failures,ensure_ascii=False)+'`','']
        (root/'dialogues.md').write_text('\n'.join(lines),encoding='utf-8')


if __name__ == '__main__':
    main()
