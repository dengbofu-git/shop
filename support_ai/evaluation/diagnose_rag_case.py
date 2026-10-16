"""Re-score saved case 14 candidates locally; never replace paired-run results."""
import argparse
import json
import os
import time
from pathlib import Path


def main():
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','dadashop.settings')
    import django
    django.setup()
    from support_ai.configuration import AgentConfig
    from support_ai.retrieval import fuse_rankings, select_evidence
    from support_ai.query_rewrite import coverage_order
    from ai_storage.reranking import rerank_candidates, RerankUnavailable

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_dir')
    args = parser.parse_args()
    root = Path(args.run_dir).resolve()
    output = root/'case14-rank-diagnostic.json'
    if output.exists():
        raise RuntimeError('Diagnostic exists; preserve its observations')
    manifest = json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    config = AgentConfig(**manifest['configuration'])
    records = [json.loads(line) for line in (root/'results.jsonl').read_text(encoding='utf-8').splitlines()]
    corpus = json.loads((root/'corpus.json').read_text(encoding='utf-8'))
    chunks = {c['id']:{'chunk_id':c['id'],'document_id':c['document_id'],'text':c['text'],
               'metadata':c['metadata'],'source_title':c['document__title'],
               'source_reference':c['document__source_reference']} for c in corpus}
    a,b = (next(r for r in records if r['case_id']==14 and r['arm']==arm) for arm in ('single_query','rewrite'))
    original = next(t['data']['question'] for t in a['audit']['tool_results'] if t['tool']=='introduce_tea')
    raw_a = [dict(chunks[c],vector_rank=i+1) for i,c in enumerate(a['vector_routes'][0]['chunk_ids'])]
    pools = [[dict(chunks[c]) for c in route['chunk_ids']] for route in b['vector_routes']]
    initial_routes = sum(q['round']==0 for q in b['retrieval'][0]['queries'])
    pool_b = fuse_rankings(pools[:initial_routes],config.retrieval_candidates)
    pooled_b = fuse_rankings(pools,config.retrieval_candidates)
    bilingual = ' | '.join(q['query'] for q in b['retrieval'][0]['queries'][:2])[:2400]
    english = b['retrieval'][0]['queries'][1]['query']
    plans = [('A_exact_query_pool',original,raw_a), ('B_exact_first_round',bilingual,pool_b),
             ('B_exact_second_round',bilingual,pooled_b), ('B_pool_english_anchor_only',english,pool_b)]
    results = []
    for name,query,pool in plans:
        print(json.dumps({'event':'diagnostic_start','name':name,'candidates':len(pool)},ensure_ascii=False),flush=True)
        started = time.perf_counter()
        row = {'name':name,'query':query,'candidate_ids':[c['chunk_id'] for c in pool]}
        try:
            ranked = rerank_candidates(query,pool,config)
            selected = select_evidence(coverage_order(original,ranked),config) if name.startswith('B_') else select_evidence(ranked,config)
            row.update(status='success',ranking=[{'chunk_id':r['chunk_id'],'rank':r['rerank_rank'],
                       'score':r['rerank_score'],'document_id':r['document_id']} for r in ranked],
                       selected_ids=[e['chunk_id'] for e in selected],
                       gold_74=next(({'rank':r['rerank_rank'],'score':r['rerank_score']} for r in ranked if r['chunk_id']==74),None),
                       first_five_before_source_limit=[r['chunk_id'] for r in ranked[:5]])
        except RerankUnavailable as exc:
            row.update(status='unavailable',reason=exc.reason)
        row['seconds'] = round(time.perf_counter()-started,3)
        results.append(row)
        output.write_text(json.dumps({'purpose':'diagnostic only; original A/B records unchanged','results':results},ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps({'event':'diagnostic_done',**{k:v for k,v in row.items() if k not in ('ranking','query','candidate_ids')}},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
