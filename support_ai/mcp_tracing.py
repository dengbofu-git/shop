"""Bounded content-free spans over the signed private channel, never tool DTOs.

The child only buffers OTel spans; the host owns database/OTLP export. Local
stdio processes share a wall clock. Durations are measured by OTel in ns.
"""
import math
import re
import time
from contextlib import contextmanager
from contextvars import ContextVar
from types import SimpleNamespace

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.resources import Resource
from opentelemetry.trace import NonRecordingSpan, SpanContext, TraceFlags, Status, StatusCode

from . import telemetry

MAX_SPANS = 160
HEX16 = re.compile(r'^[0-9a-f]{16}$')
HEX32 = re.compile(r'^[0-9a-f]{32}$')
NAMES = frozenset({
    'mcp.backend.spawn', 'mcp.backend.ready', 'mcp.backend.call', 'mcp.backend.authorize',
    'knowledge.retrieve', 'knowledge.cache', 'knowledge.query_rewrite', 'knowledge.embedding',
    'embedding.bge-m3', 'knowledge.vector_search', 'knowledge.keyword_search',
    'knowledge.hybrid_ready', 'knowledge.rrf', 'knowledge.rerank', 'knowledge.rerank.skipped', 'knowledge.retry',
    'knowledge.recall', 'knowledge.vector_route',
    'knowledge.select_context', 'knowledge.cache_write', 'chat.deepseek',
})
TOTAL_KEYS = frozenset({'agent.llm.calls', 'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens',
    'agent.retrieval.hits', 'agent.rerank.calls', 'agent.rerank.fallbacks', 'agent.rerank.failures'})
_remote = ContextVar('agent_remote_observation', default=None)


class _NullMetric:
    def add(self, *args, **kwargs):
        pass

    record = add


def clean_attributes(attributes):
    result = {}
    for key, value in attributes.items():
        if key not in telemetry.SAFE_ATTRIBUTES:
            continue
        values = value if isinstance(value, (list, tuple)) else [value]
        if len(values) <= 100 and all(type(v) in (str, int, float, bool) and
                (not isinstance(v, str) or len(v) <= 160) and
                (not isinstance(v, float) or math.isfinite(v)) for v in values):
            result[key] = value
    return result


def outgoing_context():
    session = telemetry._session.get()
    current = trace.get_current_span().get_span_context()
    if not session or not session.span or not current.is_valid:
        return None
    return {'trace_id': format(current.trace_id, '032x'), 'parent_span_id': format(current.span_id, '016x')}


def _context(value):
    if (not isinstance(value, dict) or not isinstance(value.get('trace_id'), str) or
            not isinstance(value.get('parent_span_id'), str) or not HEX32.fullmatch(value['trace_id']) or
            not HEX16.fullmatch(value['parent_span_id']) or
            int(value['trace_id'], 16) == 0 or int(value['parent_span_id'], 16) == 0):
        return None
    return trace.set_span_in_context(NonRecordingSpan(SpanContext(
        int(value['trace_id'], 16), int(value['parent_span_id'], 16), True, TraceFlags(1))))


class _Buffer(SpanExporter):
    def __init__(self):
        self.rows, self.dropped = [], 0

    def export(self, spans):
        for span in spans:
            if span.name not in NAMES:
                continue
            if len(self.rows) >= MAX_SPANS:
                self.dropped += 1
                # Windows wall timestamps can tie. Parents finish last: retain
                # them and evict a leaf rather than producing dangling children.
                parents = {r['parent_span_id'] for r in self.rows}
                leaves = [r for r in self.rows if r['span_id'] not in parents]
                latest = max(leaves, key=lambda r:r['start_ns'])
                ancestor = format(span.context.span_id,'016x') in parents
                if not ancestor and latest['start_ns'] <= span.start_time:
                    continue
                self.rows.remove(latest)
            self.rows.append(dict(name=span.name, span_id=format(span.context.span_id, '016x'),
                parent_span_id=format(span.parent.span_id, '016x'), start_ns=span.start_time,
                end_ns=span.end_time, status='ERROR' if span.status.status_code == StatusCode.ERROR else 'OK',
                attributes=clean_attributes(dict(span.attributes))))
        return SpanExportResult.SUCCESS


@contextmanager
def remote_observation(parent, config, bridge_spans=()):
    """An invalid/missing trace disables observation, never authorization or tools."""
    context = _context(parent)
    if context is None or not config.telemetry_enabled:
        yield None
        return
    provider, buffer = TracerProvider(resource=Resource({'service.name':'tea_saas-mcp-backend'}),
                                     shutdown_on_exit=False), _Buffer()
    provider.add_span_processor(SimpleSpanProcessor(buffer))
    tracer = provider.get_tracer('tea_saas.mcp.backend')
    metric = _NullMetric()
    runtime = SimpleNamespace(tracer=tracer, tokens=metric, model_duration=metric,
                             rerank_calls=metric, rerank_duration=metric, rerank_candidates=metric)
    session = telemetry.Session(runtime, config)
    report = {'trace_id': parent['trace_id'], 'parent_span_id': parent['parent_span_id']}
    try:
        # Startup spans have already ended before Django can collect them.
        for row in list(bridge_spans)[:2]:
            if (isinstance(row, dict) and row.get('name') in ('mcp.backend.spawn', 'mcp.backend.ready') and
                    type(row.get('start_ns')) is int and type(row.get('end_ns')) is int and
                    time.time_ns()-150_000_000_000 <= row['start_ns'] <= row['end_ns'] <= time.time_ns()):
                span = tracer.start_span(row['name'], context=context, start_time=row['start_ns'])
                span.set_status(Status(StatusCode.OK))
                span.end(end_time=row['end_ns'])
        with tracer.start_as_current_span('mcp.backend.call', context=context,
                record_exception=False, set_status_on_exception=False) as root:
            session.span = root
            session.callback = telemetry.ModelTelemetry(session)
            token = telemetry._session.set(session)
            remote_token = _remote.set(session)
            try:
                yield report
            finally:
                _remote.reset(remote_token)
                telemetry._session.reset(token)
        report.update(spans=buffer.rows, totals=session.totals, dropped=buffer.dropped)
    finally:
        provider.shutdown()


def remote_callback():
    session = _remote.get()
    return session.callback if session else None


def remote_result(status):
    session = _remote.get()
    if session:
        session.span.set_attribute('agent.mcp.status', status)
        session.span.set_status(Status(StatusCode.ERROR if status == 'error' else StatusCode.OK))


def import_report(report, expected):
    """Validate the entire graph before publishing; malformed telemetry is fail-open."""
    session = telemetry._session.get()
    if not session or not session.span or expected is None:
        return 'disabled'
    try:
        if (not isinstance(report, dict) or any(report.get(k) != expected[k] for k in expected) or
                not isinstance(report.get('spans'), list) or len(report['spans']) > MAX_SPANS or
                not isinstance(report.get('totals'), dict) or type(report.get('dropped')) is not int or
                not 0 <= report['dropped'] <= 10000):
            raise ValueError()
        rows = report['spans']
        ids = set()
        now = time.time_ns()
        for row in sorted(rows, key=lambda r: r['start_ns']):
            if (row['name'] not in NAMES or not HEX16.fullmatch(row['span_id']) or
                    int(row['span_id'], 16) == 0 or row['span_id'] in ids or row['span_id'] == expected['parent_span_id'] or
                    not HEX16.fullmatch(row['parent_span_id']) or
                    type(row['start_ns']) is not int or type(row['end_ns']) is not int or
                    not now - 150_000_000_000 <= row['start_ns'] <= row['end_ns'] <= now + 2_000_000_000 or
                    row['status'] not in ('OK', 'ERROR') or not isinstance(row['attributes'], dict)):
                raise ValueError()
            ids.add(row['span_id'])
        ordered, pending, parents = [], list(rows), {expected['parent_span_id']}
        while pending:
            ready = sorted((r for r in pending if r['parent_span_id'] in parents), key=lambda r:r['start_ns'])
            if not ready:
                raise ValueError()
            for row in ready:
                ordered.append(row); pending.remove(row); parents.add(row['span_id'])
        if any(k not in TOTAL_KEYS or type(v) is not int or not 0 <= v <= 10_000_000
               for k, v in report['totals'].items()):
            raise ValueError()
    except (KeyError, TypeError, ValueError, AttributeError):
        return 'invalid'
    for row in ordered:
        parent = _context(dict(trace_id=expected['trace_id'], parent_span_id=row['parent_span_id']))
        try:
            _publish_row(session, expected['trace_id'], row, parent)
        except Exception:
            return 'export_failed'
    with session.lock:
        for key, value in report['totals'].items():
            session.totals[key] = session.totals.get(key, 0) + value
        if report['dropped']:
            session.totals['agent.mcp.truncated_spans'] = session.totals.get('agent.mcp.truncated_spans',0)+report['dropped']
    try:
        _record_metrics(session, rows)
    except Exception:
        return 'export_failed'
    return 'truncated' if report['dropped'] else 'complete'


def _record_metrics(session, rows):
    for row in rows:
        attrs = row['attributes']
        seconds = (row['end_ns']-row['start_ns'])/1e9
        if row['name'] == 'chat.deepseek':
            labels = {'gen_ai.request.model':session.config.model, 'gen_ai.operation.name':'chat'}
            session.runtime.model_duration.record(seconds, labels)
            for kind in ('input','output'):
                value=attrs.get('gen_ai.usage.'+kind+'_tokens',0)
                value=value if type(value) is int and value>=0 else 0
                session.runtime.tokens.add(value,
                                           dict(labels, **{'gen_ai.token.type':kind}))
        if row['name'] == 'knowledge.rerank':
            labels = {'agent.rerank.model':attrs.get('agent.rerank.model','unknown'),
                      'outcome':attrs.get('agent.rerank.status','failed'),
                      'reason':attrs.get('agent.rerank.reason','')}
            session.runtime.rerank_calls.add(1,labels)
            session.runtime.rerank_duration.record(seconds,labels)
            session.runtime.rerank_candidates.record(attrs.get('agent.rerank.candidates',0),
                                                     {'agent.rerank.model':labels['agent.rerank.model']})


def _publish_row(session, trace_id, row, parent):
    from opentelemetry.sdk.trace import ReadableSpan
    span = ReadableSpan(name=row['name'],
        context=SpanContext(int(trace_id, 16), int(row['span_id'], 16), False, TraceFlags(1)),
        parent=trace.get_current_span(parent).get_span_context(),
        resource=session.runtime.provider.resource,
        attributes=clean_attributes(row['attributes']), start_time=row['start_ns'], end_time=row['end_ns'],
        status=Status(StatusCode.ERROR if row['status'] == 'ERROR' else StatusCode.OK))
    # Both local projection and optional OTLP use the exact same remote IDs.
    session.runtime.publish_remote_span(span)
