"""Timing-only trace analysis. Inclusive parents are never added to children."""
from collections import defaultdict
from datetime import datetime, timezone


def _milliseconds(value):
    if isinstance(value,str):
        value=datetime.fromisoformat(value.replace('Z','+00:00'))
    if value.tzinfo is None:
        value=value.replace(tzinfo=timezone.utc)
    return value.timestamp()*1000


def _covered(intervals):
    end,total=None,0.
    for left,right in sorted(intervals):
        if end is None or left >= end:
            total += right-left
        elif right > end:
            total += right-end
        end=max(end or right,right)
    return total


def analyze_spans(spans):
    rows=[dict(r) for r in spans]
    if not rows:
        raise ValueError('No recorded spans')
    root=next((r for r in rows if r['name']=='support.chat' and not r['parent_span_id']),None)
    if root is None:
        raise ValueError('A support.chat root is required')
    base=_milliseconds(root['started_at'])
    starts={r['span_id']:_milliseconds(r['started_at'])-base for r in rows}
    children=defaultdict(list)
    for r in rows:
        children[r['parent_span_id']].append(r)
    results=[]
    for r in rows:
        left=starts[r['span_id']];right=left+r['duration_ms']
        intervals=[]
        for child in children[r['span_id']]:
            a=max(left,starts[child['span_id']]);b=min(right,starts[child['span_id']]+child['duration_ms'])
            if b>a:
                intervals.append((a,b))
        results.append(dict(name=r['name'],span_id=r['span_id'],parent_span_id=r['parent_span_id'],
            start_ms=round(left,3),inclusive_ms=round(r['duration_ms'],3),
            self_ms=round(max(0,r['duration_ms']-_covered(intervals)),3),status=r['status'],
            attributes={k:v for k,v in r.get('attributes',{}).items() if k in (
                'agent.cache.kind','agent.cache.status','agent.rerank.status','agent.rerank.candidates',
                'agent.retrieval.hits','agent.retrieval.round','agent.retrieval.query_index',
                'agent.mcp.telemetry','agent.mcp.status')}))
    groups=defaultdict(lambda:dict(calls=0,inclusive_ms=0.,self_ms=0.))
    for row in results:
        item=groups[row['name']];item['calls']+=1
        item['inclusive_ms']+=row['inclusive_ms'];item['self_ms']+=row['self_ms']
    for item in groups.values():
        for key in ('inclusive_ms','self_ms'):
            item[key]=round(item[key],3)
    names=set(groups)
    warnings=[]
    if any(n.startswith('mcp.') for n in names) and 'mcp.backend.call' not in names:
        warnings.append('MCP backend segments were not recorded; do not attribute the whole MCP wait to SQL or Embedding.')
    if any(r['parent_span_id'] and r['parent_span_id'] not in starts for r in rows):
        warnings.append('Some parents are missing; self times are upper bounds for the available projection.')
    if any(r.get('attributes',{}).get('agent.mcp.telemetry') not in (None,'complete','disabled') for r in rows):
        warnings.append('At least one MCP telemetry report is incomplete or unavailable.')
    if root.get('attributes',{}).get('agent.mcp.truncated_spans',0):
        warnings.append('Backend spans were truncated at the bounded telemetry limit.')
    hotspots=sorted((r for r in results if r['self_ms']>=1),key=lambda r:-r['self_ms'])[:10]
    suggestions=[]
    for row in hotspots:
        name=row['name']
        if name=='mcp.initialize' and 'mcp.session.connect' in names:
            hint='Inspect HTTP connection, worker queue and request-session initialization; resident processes are already warm.'
        elif name in ('mcp.sdk.startup','mcp.initialize','mcp.backend.ready'):
            hint='Measure cold process/import cost; consider a resident backend only with per-request grant and state isolation.'
        elif name=='knowledge.embedding':
            hint='Compare model cold/warm latency and embedding cache hits; batch independent embeddings within existing budgets.'
        elif name in ('knowledge.vector_search','knowledge.keyword_search','knowledge.cache'):
            hint='Inspect DB connect versus query cost and EXPLAIN on an isolated representative dataset; preserve ACL and epoch checks.'
        elif name=='knowledge.rerank':
            hint='Compare candidate count, service queue and model residency; cap candidates before scoring and keep fallback policy.'
        elif name in ('mcp.rpc','mcp.search_knowledge','mcp.backend.call'):
            hint='Inspect uncovered handoff/serialization intervals and missing segments before assigning a cause.'
        else:
            continue
        if hint not in suggestions:
            suggestions.append(hint)
    return dict(duration_ms=round(root['duration_ms'],3),
        semantics='inclusive contains children; self subtracts the union of direct child intervals; do not sum inclusive rows',
        nodes=sorted(results,key=lambda r:r['start_ms']),stages=dict(groups),hotspots=hotspots,
        warnings=warnings,optimization_candidates=suggestions)
