"""Paired public-knowledge replay: fixed Agent, single-query vs rewrite retrieval.

Records returned graph state and intermediate evidence without changing results.
Only the evaluation process overrides settings; serving configuration is untouched.
"""
import argparse
import ast
import hashlib
import json
import os
import statistics
import time
from dataclasses import asdict, replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def function_body(path, name):
    tree = ast.parse(Path(path).read_text(encoding='utf-8'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.dump(ast.Module(body=node.body, type_ignores=[]), include_attributes=False)


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tea_saas.settings')
    import django
    django.setup()
    from django.conf import settings
    from django.db import connection
    from django.test.utils import override_settings
    from django.utils import timezone
    from langchain_core.callbacks import BaseCallbackHandler
    from ai_storage.models import KnowledgeChunk
    from support_ai import preview, retrieval
    from support_ai.configuration import effective_configuration
    from support_ai.models import SupportConversation, SupportTurn, AgentSpan
    from support_ai.query_rewrite import QueryPolicy

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', required=True)
    parser.add_argument('--expected-database-name', required=True)
    args = parser.parse_args()
    root = Path(args.output_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    if (root/'manifest.json').exists():
        raise RuntimeError('Existing evaluation detected; choose a fresh output directory')
    cases_path = Path(__file__).with_name('rag_rewrite_cases.json')
    cases = json.loads(cases_path.read_text(encoding='utf-8'))
    config = replace(effective_configuration(), telemetry_enabled=False, export_enabled=False)
    corpus = list(KnowledgeChunk.objects.filter(document__visibility='public',document__status='published',
        embedding_space__key=settings.AI_EMBEDDING_SPACE_KEY,embedding__isnull=False).values(
        'id','text','metadata','document_id','document__title','document__source_reference').order_by('id'))
    corpus_text = json.dumps(corpus,ensure_ascii=False,sort_keys=True,default=str)
    corpus_ids = {r['id'] for r in corpus}
    assert len(cases)==15 and all(set(c['relevant_ids']) <= corpus_ids for c in cases)
    with connection.cursor() as cursor:
        cursor.execute('SELECT DATABASE(), @@server_uuid')
        database = cursor.fetchone()
    if database != (args.expected_database_name,'6b35ae3b-0afa-11f1-808b-2632d3201c4a'):
        raise RuntimeError('Unexpected business database target')
    sources = ['support_ai/'+p for p in ('retrieval.py','query_rewrite.py','tool_services.py','workflow.py',
        'planning.py','tea_explanation.py','model_client.py','preview.py','pii.py','context.py','configuration.py')]
    sources += ['ai_storage/knowledge.py','ai_storage/embeddings.py','ai_storage/reranking.py']
    before_hashes = {p:digest(p) for p in sources}
    old_retrieval = root.parent/'before'/'support_ai'/'retrieval.py'
    baseline_equivalent = function_body(old_retrieval,'retrieve_knowledge') == function_body(
        'support_ai/retrieval.py','_retrieve_single')
    if not baseline_equivalent:
        raise RuntimeError('Single-query baseline body differs from saved pre-rewrite source')
    counts = lambda:{'turns':SupportTurn.objects.count(),'conversations':SupportConversation.objects.count(),
                     'spans':AgentSpan.objects.count()}
    before_counts = counts()
    manifest = {'started_at':timezone.now().isoformat(),'protocol':{
        'design':'15 cases, one paired run each, AB/BA alternating, fresh public sessions',
        'baseline':'same Agent 0.9.0, SUPPORT_RAG_QUERY_ENABLED=False; body equals saved 0.8.1 retrieval',
        'candidate':'same Agent 0.9.0, SUPPORT_RAG_QUERY_ENABLED=True, current bounded policy',
        'scope':'public; no customer history, buyer identity, business writes or telemetry',
        'metrics':'preregistered support-group coverage, relevant-id precision, actual answers, latency and tokens',
        'limits':'one sample per arm; no independently verified external facts; no global accuracy claim'},
        'configuration':asdict(config),'query_policy':asdict(QueryPolicy.current()),'cases':cases,
        'dataset_sha256':digest(cases_path),'source_sha256':before_hashes,
        'single_query_baseline_body_equivalent':baseline_equivalent,'business_counts_before':before_counts,
        'corpus_sha256':hashlib.sha256(corpus_text.encode()).hexdigest(),'public_chunk_count':len(corpus)}
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    (root/'corpus.json').write_text(json.dumps(corpus,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    records, captured, intermediate, routes, structured = [], {}, [], [], []
    original_graph = preview.build_graph

    class CaptureCalls(BaseCallbackHandler):
        def on_llm_end(self, response, **kwargs):
            for group in response.generations:
                for generation in group:
                    for call in getattr(getattr(generation,'message',None),'tool_calls',[]):
                        # Only schema outputs; never record hidden reasoning or credentials.
                        if call.get('name') in ('QueryTranslations','FiniteIntents'):
                            structured.append({'name':call['name'],'args':call.get('args')})

    class FrozenSession(preview.PreviewSession):
        def configuration(self):
            return config

    def observe_graph(*a, **kw):
        graph = original_graph(*a, **kw)
        def invoke(*ia, **ikw):
            ikw['config'] = dict(ikw.get('config') or {})
            ikw['config']['callbacks'] = list(ikw['config'].get('callbacks') or []) + [CaptureCalls()]
            state = graph.invoke(*ia, **ikw)
            captured['graph'] = preview.safe_record({k:state.get(k) for k in
                ('resolved_question','plan','tool_results','compliance_blocked')})
            return state
        return SimpleNamespace(invoke=invoke)

    def score(case, evidence):
        ids = {v['chunk_id'] for v in evidence}
        groups, relevant = case['support_groups'], set(case['relevant_ids'])
        covered = sum(bool(ids & set(g)) for g in groups)
        return {'selected_ids':[v['chunk_id'] for v in evidence], 'support_groups_hit':covered,
                'support_groups_total':len(groups),
                'support_group_coverage':covered/len(groups) if groups else None,
                'all_available_support':covered==len(groups) if groups else None,
                'labelled_relevant_precision':len(ids & relevant)/len(ids) if ids and relevant else None}

    with patch('support_ai.preview.build_graph',side_effect=observe_graph):
        for case in cases:
            arms = ('single_query','rewrite') if case['id'] % 2 else ('rewrite','single_query')
            for arm in arms:
                captured.clear(); intermediate.clear(); routes.clear(); structured.clear()
                print(json.dumps({'event':'start','case_id':case['id'],'arm':arm,'message':case['message']},ensure_ascii=False),flush=True)
                with override_settings(SUPPORT_RAG_QUERY_ENABLED=arm=='rewrite'):
                    session = FrozenSession(log_dir=root/'sessions'/arm)
                    try:
                        record = session.ask(case['message'])
                    except Exception:
                        record = session.last_error or {'event':'error','error_type':'UnknownError'}
                graph = captured.get('graph') or {}
                evidence = [e for t in graph.get('tool_results',[]) for e in t.get('data',{}).get('evidence',[])]
                record = preview.safe_record(dict(record,case_id=case['id'],arm=arm,scene=case['scene'],
                    audit=graph, intermediate_evidence=list(intermediate), vector_routes=list(routes),
                    structured_outputs=list(structured), evidence_metrics=score(case,evidence),
                    first_round_metrics=None,
                    capture_scope='MCP returned evidence and audit; backend intermediate/route interception is unavailable'))
                records.append(record)
                with (root/'results.jsonl').open('a',encoding='utf-8') as stream:
                    stream.write(json.dumps(record,ensure_ascii=False,default=str)+'\n')
                print(json.dumps({'event':'done','case_id':case['id'],'arm':arm,'seconds':record.get('elapsed_seconds'),
                    'calls':record.get('model_calls'),'coverage':record['evidence_metrics'],
                    'rewrite':[{'states':a['rewrite_status'],'queries':len(a['queries']),'retry':a['retry'],
                                'adopted':a['retry_adopted'],'remaining':a.get('remaining_issues')} for a in record.get('retrieval',[])],
                    'answer':record.get('response',{}).get('answer','')[:140]},ensure_ascii=False),flush=True)

    after_corpus = list(KnowledgeChunk.objects.filter(document__visibility='public',document__status='published',
        embedding_space__key=settings.AI_EMBEDDING_SPACE_KEY,embedding__isnull=False).values(
        'id','text','metadata','document_id','document__title','document__source_reference').order_by('id'))
    summary = {'completed_at':timezone.now().isoformat(),'completed_runs':len(records),
        'source_unchanged':before_hashes=={p:digest(p) for p in sources},
        'corpus_unchanged':corpus==after_corpus,'business_counts_before':before_counts,'business_counts_after':counts(),
        'arms':{}}
    for arm in ('single_query','rewrite'):
        rows = [r for r in records if r['arm']==arm]
        metrics = [r['evidence_metrics'] for r in rows]
        denominator = sum(m['support_groups_total'] for m in metrics)
        summary['arms'][arm] = {
            'runs':len(rows),'returned_turns':sum(r['event']=='turn' for r in rows),
            'compliance_blocks':sum(r.get('compliance_blocked',False) for r in rows),
            'support_groups_hit':sum(m['support_groups_hit'] for m in metrics),'support_groups_total':denominator,
            'support_group_coverage':sum(m['support_groups_hit'] for m in metrics)/denominator if denominator else None,
            'all_available_support_cases':sum(m['all_available_support'] is True for m in metrics),
            'support_eligible_cases':sum(m['support_group_coverage'] is not None for m in metrics),
            'macro_labelled_relevant_precision':statistics.mean(m['labelled_relevant_precision'] for m in metrics if m['labelled_relevant_precision'] is not None),
            'mean_seconds':statistics.mean(r.get('elapsed_seconds',0) for r in rows),
            'median_seconds':statistics.median(r.get('elapsed_seconds',0) for r in rows),
            'model_calls':sum(r.get('model_calls',0) for r in rows),
            'input_tokens':sum(r.get('input_tokens',0) for r in rows),'output_tokens':sum(r.get('output_tokens',0) for r in rows),
            'vector_searches':sum(len(r.get('vector_routes',[])) for r in rows),
            'retry_cases':sum(any(a['retry'] for a in r.get('retrieval',[])) for r in rows),
            'retry_adopted_cases':sum(any(a['retry_adopted'] for a in r.get('retrieval',[])) for r in rows),
        }
    (root/'run-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'event':'complete',**summary},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
