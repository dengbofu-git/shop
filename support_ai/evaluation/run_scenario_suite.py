"""Run 15 preregistered ecommerce questions against the unchanged public Agent.

The graph proxy observes returned state only; it never alters model/tool results.
"""
import argparse
import hashlib
import json
import os
import time
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tea_saas.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.utils import timezone
    from support_ai import preview
    from support_ai.models import SupportTurn, SupportConversation, AgentSpan
    from support_ai.recommendations import available_products

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    args = parser.parse_args()
    root = Path(args.output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root / 'manifest.json').exists():
        raise RuntimeError('Existing run detected; use a fresh output directory')
    dataset_path = Path(__file__).with_name('scenario_suite_15.json')
    dataset = json.loads(dataset_path.read_text(encoding='utf-8'))
    assert len(dataset) == 15 and [c['id'] for c in dataset] == list(range(1, 16))
    files = ['support_ai/' + p for p in ('preview.py','workflow.py','planning.py','contracts.py','context.py',
        'execution.py','tool_services.py','recommendation_options.py','recommendations.py','tea_explanation.py',
        'retrieval.py','configuration.py','model_client.py','pii.py','diagnostics.py')]
    hashes = lambda: {p: hashlib.sha256((settings.BASE_DIR / p).read_bytes()).hexdigest() for p in files}
    counts = lambda: {'turns':SupportTurn.objects.count(),'conversations':SupportConversation.objects.count(),'spans':AgentSpan.objects.count()}
    catalog = {r['id']: r for r in available_products().values('id','name','spu__name','spu__catalog__name','price','available_stock')}
    source_hashes, before = hashes(), counts()
    manifest = {'started_at':timezone.now().isoformat(),'dataset_sha256':hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
                'agent_source_sha256':source_hashes,'business_counts_before':before,'scope':'public','telemetry':False,
                'catalog_snapshot':list(catalog.values()),'cases':dataset}
    (root / 'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    sessions, records, by_case, captured = {}, [], {}, {}
    original_build = preview.build_graph

    def observe_graph(*args, **kwargs):
        graph = original_build(*args, **kwargs)
        def invoke(*invoke_args, **invoke_kwargs):
            state = graph.invoke(*invoke_args, **invoke_kwargs)
            captured['audit'] = preview.safe_record({k:state.get(k) for k in
                ('safe_message','resolved_question','plan','tool_results','compliance_blocked','deterministic_composition')})
            return state
        return SimpleNamespace(invoke=invoke)

    def checks(case, record):
        response = record.get('response', {})
        cards = response.get('recommendations', [])
        audit = record.get('audit') or {}
        tools = audit.get('tool_results') or []
        values = {'intent_sequence':response.get('intents') in case['expected_intents'],
                  'no_runtime_error':record.get('event') == 'turn',
                  'not_compliance_blocked':not record.get('compliance_blocked',False)}
        known = all(p.get('sku_id') in catalog for p in cards)
        values['catalog_identity_and_price'] = known and all(
            Decimal(p['price']) == Decimal(str(catalog[p['sku_id']]['price']))
            and p['category'] == catalog[p['sku_id']]['spu__catalog__name'] for p in cards)
        if case.get('categories') and cards:
            values['allowed_categories'] = all(p['category'] in case['categories'] for p in cards)
        if case.get('price_max'):
            values['unit_price_limit'] = all(Decimal(p['price']) <= Decimal(case['price_max']) for p in cards)
        if case.get('excluded'):
            values['excluded_categories'] = all(p['category'] not in case['excluded'] for p in cards)
        kind = case['kind']
        if kind in ('products','reverse_mixed'):
            values['product_count'] = len(cards) == case['count']
        if case.get('different_from'):
            previous = by_case[case['different_from']].get('response',{}).get('recommendations',[])
            values['changed_products'] = not {p['sku_id'] for p in cards} & {p['sku_id'] for p in previous}
        if kind in ('groups','explain_products'):
            groups = response.get('recommendation_groups',[])
            values['group_coverage'] = [g['category'] for g in groups] == case['categories']
            values['per_group_count'] = len(cards) == len(case['categories']) * case['per_group'] and all(
                len(g['recommendations']) == case['per_group'] for g in groups)
        if kind == 'explain_products':
            values['explanation_coverage'] = response.get('explained_categories') == case['categories']
            values['knowledge_dependency'] = any(s.get('knowledge_from') for s in response.get('task_plan',{}).get('steps',[]))
        if kind in ('knowledge','country_knowledge','reverse_mixed','explain_products','knowledge_details'):
            values['knowledge_sources_present'] = bool(response.get('knowledge_sources'))
        if kind in ('knowledge','country_knowledge'):
            values['no_unrequested_products'] = not cards
        if kind in ('details','knowledge_details'):
            earlier = by_case[case['reference_case']].get('response',{}).get('recommendations',[])
            expected_id = earlier[case['position']-1]['sku_id'] if len(earlier) >= case['position'] else None
            detail = next((t for t in tools if t['tool'] == 'get_product_details'),None)
            values['same_product_reference'] = bool(detail and detail['status'] == 'success'
                                                      and detail['data'].get('sku_id') == expected_id)
            if detail and detail['status'] == 'success' and expected_id in catalog:
                values['live_detail_facts'] = (Decimal(detail['data']['price']) == Decimal(str(catalog[expected_id]['price']))
                    and detail['data']['available_stock'] == catalog[expected_id]['available_stock'])
        if kind == 'no_match':
            feasible = [v for v in catalog.values() if v['spu__catalog__name'] in case['categories'] and Decimal(str(v['price'])) <= Decimal(case['price_max'])]
            values['no_match_ground_truth'] = not feasible and not cards and response.get('recommendation_status') == 'NO_MATCH'
        if kind == 'budget_clarification':
            values['budget_scope_clarified'] = not cards and response.get('clarification_required',False) and any(
                word in response.get('answer','') for word in ('总预算','单价','每份','每盒','采购数量'))
        if kind == 'order_boundary':
            values['order_scope_guard'] = not cards and any(t['tool']=='get_order_status' and t['status']=='needs_clarification' for t in tools)
        if case.get('previous'):
            values['history_available'] = record.get('context_turns',0) > 0
        expected_clarify = kind in ('budget_clarification','order_boundary')
        if not expected_clarify:
            values['tools_completed'] = bool(tools) and all(t['status'] in ('success','no_match') for t in tools)
        return values

    with patch('support_ai.preview.build_graph', side_effect=observe_graph):
        for case in dataset:
            if case['session'] not in sessions:
                sessions[case['session']] = preview.PreviewSession(log_dir=root/'sessions')
            session = sessions[case['session']]
            captured.clear()
            config = asdict(session.configuration())
            print(json.dumps({'event':'case_start','case_id':case['id'],'message':case['message']},ensure_ascii=False),flush=True)
            try:
                record = session.ask(case['message'])
            except Exception:
                record = session.last_error or {'event':'error','error_type':'UnknownPreviewError'}
            record = preview.safe_record(dict(record,case_id=case['id'],scenario=case['kind'],configuration=config,
                                             expected_intents=case['expected_intents'],audit=captured.get('audit')))
            record['checks'] = checks(case,record)
            records.append(record)
            by_case[case['id']] = record
            with (root/'results.jsonl').open('a',encoding='utf-8') as stream:
                stream.write(json.dumps(record,ensure_ascii=False,default=str)+'\n')
            response = record.get('response',{})
            print(json.dumps({'event':'case_done','case_id':case['id'],'intents':response.get('intents'),
                'tasks':response.get('tasks'),'products':len(response.get('recommendations',[])),
                'seconds':record.get('elapsed_seconds'),'calls':record.get('model_calls'),
                'failed_checks':[k for k,v in record['checks'].items() if not v],
                'answer':response.get('answer','')[:200]},ensure_ascii=False),flush=True)

    summary = {'completed_at':timezone.now().isoformat(),'cases':len(records),
               'returned_turns':sum(r['event']=='turn' for r in records),
               'exact_intent_matches':sum(r['checks']['intent_sequence'] for r in records),
               'all_automatic_checks_pass':sum(all(r['checks'].values()) for r in records),
               'business_counts_before':before,'business_counts_after':counts(),
               'agent_code_unchanged':source_hashes==hashes(),
               'runtime':next(iter(sessions.values())).status(),
               'elapsed_seconds':[r.get('elapsed_seconds') for r in records],
               'model_calls':sum(r.get('model_calls',0) for r in records),
               'input_tokens':sum(r.get('input_tokens',0) for r in records),
               'output_tokens':sum(r.get('output_tokens',0) for r in records)}
    (root/'run-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'event':'suite_done',**summary},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
