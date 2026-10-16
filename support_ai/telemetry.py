"""OpenTelemetry spans/metrics for the Agent, with a content-free local projection."""

import atexit
import logging
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from langchain_core.callbacks import BaseCallbackHandler
from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SimpleSpanProcessor, SpanExporter, SpanExportResult
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader, MetricExportResult
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.trace import SpanKind, Status, StatusCode

logger = logging.getLogger(__name__)
_session = ContextVar('support_agent_observation', default=None)
_lock = threading.RLock()
_active = None

# Explicit allowlist: no prompts, completions, identities, URLs, exception messages or stacks.
SAFE_ATTRIBUTES = frozenset({
    'gen_ai.operation.name', 'gen_ai.provider.name', 'gen_ai.request.model', 'gen_ai.response.model',
    'gen_ai.usage.input_tokens', 'gen_ai.usage.output_tokens', 'agent.intent', 'agent.config.revision',
    'agent.llm.calls', 'agent.retrieval.hits', 'agent.compliance.blocked', 'error.type',
    'agent.rerank.model', 'agent.rerank.revision', 'agent.rerank.candidates', 'agent.rerank.reason',
    'agent.rerank.input_ids', 'agent.rerank.output_ids', 'agent.rerank.scores', 'agent.retrieval.selected_ids',
    'agent.rerank.calls', 'agent.rerank.fallbacks', 'agent.rerank.failures',
    'agent.context.turns', 'agent.context.chars', 'agent.context.resolution', 'agent.context.clarification',
    'agent.plan.source', 'agent.plan.steps', 'agent.plan.intents', 'agent.tool.step', 'agent.tool.status',
    'agent.tasks.success', 'agent.tasks.failed',
    'agent.rewrite.variants', 'agent.rewrite.rejected', 'agent.retrieval.queries',
    'agent.retrieval.retries', 'agent.retrieval.retry_reasons',
    'agent.retrieval.remaining_issues', 'agent.retrieval.retry_adopted', 'agent.rewrite.status',
})


class DatabaseSpanExporter(SpanExporter):
    def export(self, spans):
        from .models import AgentSpan
        try:
            AgentSpan.objects.bulk_create([
                AgentSpan(
                    trace_id=format(span.context.trace_id, '032x'), span_id=format(span.context.span_id, '016x'),
                    parent_span_id=format(span.parent.span_id, '016x') if span.parent else '', name=span.name,
                    started_at=datetime.fromtimestamp(span.start_time / 1e9, tz=timezone.utc),
                    duration_ms=(span.end_time - span.start_time) / 1e6,
                    status='ERROR' if span.status.status_code == StatusCode.ERROR else 'OK',
                    attributes={k: v for k, v in span.attributes.items() if k in SAFE_ATTRIBUTES},
                ) for span in spans
            ], ignore_conflicts=True)
            return SpanExportResult.SUCCESS
        except Exception as exc:
            # Monitoring must not take the customer workflow down.
            logger.warning('Agent telemetry persistence failed: %s', type(exc).__name__)
            return SpanExportResult.FAILURE


class ReportingSpanExporter(OTLPSpanExporter):
    def __init__(self, health, **kwargs):
        self.health = health
        super().__init__(**kwargs)

    def export(self, spans):
        try:
            result = super().export(spans)
            self.health['trace_export_status'] = 'success' if result == SpanExportResult.SUCCESS else 'error'
            return result
        except Exception:
            self.health['trace_export_status'] = 'error'
            return SpanExportResult.FAILURE
        finally:
            self.health['trace_export_at'] = datetime.now(timezone.utc).isoformat()


class ReportingMetricExporter(OTLPMetricExporter):
    def __init__(self, health, **kwargs):
        self.health = health
        super().__init__(**kwargs)

    def export(self, metrics_data, timeout_millis=10000, **kwargs):
        try:
            result = super().export(metrics_data, timeout_millis=timeout_millis, **kwargs)
            self.health['metric_export_status'] = 'success' if result == MetricExportResult.SUCCESS else 'error'
            return result
        except Exception:
            self.health['metric_export_status'] = 'error'
            return MetricExportResult.FAILURE
        finally:
            self.health['metric_export_at'] = datetime.now(timezone.utc).isoformat()


class Runtime:
    def __init__(self, config):
        self.key = (config.telemetry_enabled, config.export_enabled, config.otlp_endpoint)
        self.references = 0
        self.retired = False
        self.shutdown_lock = threading.Lock()
        self.closed = False
        self.provider = None
        self.meters = None
        self.health = {'trace_export_status': 'waiting' if config.export_enabled else 'disabled',
                       'metric_export_status': 'waiting' if config.export_enabled else 'disabled',
                       'trace_export_at': None, 'metric_export_at': None}
        if not config.telemetry_enabled:
            return
        resource = Resource.create({'service.name': 'dadashop-support-agent', 'service.version': '0.10.0'})
        self.provider = TracerProvider(resource=resource, shutdown_on_exit=False)
        self.provider.add_span_processor(SimpleSpanProcessor(DatabaseSpanExporter()))
        readers = []
        if config.export_enabled:
            self.provider.add_span_processor(BatchSpanProcessor(
                ReportingSpanExporter(self.health, endpoint=config.otlp_endpoint + '/v1/traces', timeout=3),
                schedule_delay_millis=1000, max_queue_size=2048,
            ))
            readers.append(PeriodicExportingMetricReader(
                ReportingMetricExporter(self.health, endpoint=config.otlp_endpoint + '/v1/metrics', timeout=3),
                export_interval_millis=5000, export_timeout_millis=4000,
            ))
        self.meters = MeterProvider(resource=resource, metric_readers=readers, shutdown_on_exit=False)
        meter = self.meters.get_meter('dadashop.support_ai')
        self.requests = meter.create_counter('agent.requests', unit='{request}')
        self.duration = meter.create_histogram('agent.request.duration', unit='s')
        self.tokens = meter.create_counter('agent.tokens', unit='{token}')
        self.model_duration = meter.create_histogram('gen_ai.client.operation.duration', unit='s')
        self.rerank_calls = meter.create_counter('agent.rerank.requests', unit='{request}')
        self.rerank_duration = meter.create_histogram('agent.rerank.duration', unit='s')
        self.rerank_candidates = meter.create_histogram('agent.rerank.candidate_count', unit='{chunk}')
        self.tracer = self.provider.get_tracer('dadashop.support_ai')

    def shutdown(self):
        with self.shutdown_lock:
            if self.closed:
                return
            self.closed = True
        if self.provider:
            self.provider.shutdown()
        if self.meters:
            self.meters.shutdown(timeout_millis=4000)


def acquire_runtime(config):
    global _active
    old = None
    with _lock:
        key = (config.telemetry_enabled, config.export_enabled, config.otlp_endpoint)
        if _active is None or _active.key != key:
            old = _active
            _active = Runtime(config)
            if old:
                old.retired = True
        _active.references += 1
        current = _active
    if old and old.references == 0:
        old.shutdown()
    return current


def release_runtime(runtime):
    with _lock:
        runtime.references -= 1
        shutdown = runtime.retired and runtime.references == 0
    if shutdown:
        runtime.shutdown()


def refresh_runtime(config):
    runtime = acquire_runtime(config)
    release_runtime(runtime)


def telemetry_status():
    with _lock:
        if _active is None:
            return {'initialized': False}
        return dict(_active.health, initialized=True, enabled=_active.key[0], export_enabled=_active.key[1])


def shutdown_telemetry():
    global _active
    with _lock:
        runtime, _active = _active, None
        if runtime:
            runtime.retired = True
    if runtime and runtime.references == 0:
        runtime.shutdown()


atexit.register(shutdown_telemetry)


class Session:
    def __init__(self, runtime, config, span=None):
        self.runtime = runtime
        self.config = config
        self.span = span
        self.lock = threading.Lock()
        self.totals = {'agent.llm.calls': 0, 'gen_ai.usage.input_tokens': 0,
                       'gen_ai.usage.output_tokens': 0, 'agent.retrieval.hits': 0}
        self.intent = 'unknown'
        self.callback = ModelTelemetry(self) if span else None

    @property
    def trace_id(self):
        return format(self.span.get_span_context().trace_id, '032x') if self.span else ''

    def finish(self, result):
        self.intent = result.get('intent', 'unknown')
        if self.span:
            self.span.set_attribute('agent.intent', self.intent)
            self.span.set_attribute('agent.compliance.blocked', result.get('compliance_blocked', False))
            if result.get('plan'):
                self.span.set_attribute('agent.plan.source', result['plan']['source'])
                self.span.set_attribute('agent.plan.steps', len(result['plan']['steps']))
                self.span.set_attribute('agent.plan.intents', tuple(result.get('intents', [])))
                statuses = [r['status'] for r in result.get('tool_results', [])]
                self.span.set_attribute('agent.tasks.success', statuses.count('success'))
                self.span.set_attribute('agent.tasks.failed', statuses.count('error'))


@contextmanager
def observe_agent(config):
    runtime = acquire_runtime(config)
    try:
        if not runtime.provider:
            yield Session(runtime, config)
            return
        with runtime.tracer.start_as_current_span(
            'support.chat', kind=SpanKind.SERVER, record_exception=False, set_status_on_exception=False,
            attributes={'gen_ai.provider.name': 'deepseek', 'gen_ai.request.model': config.model,
                        'agent.config.revision': config.revision},
        ) as root:
            session = Session(runtime, config, root)
            token = _session.set(session)
            started = time.perf_counter()
            outcome = 'success'
            try:
                yield session
                root.set_status(Status(StatusCode.OK))
            except Exception as exc:
                outcome = 'error'
                root.set_attribute('error.type', type(exc).__name__)
                root.set_status(Status(StatusCode.ERROR))
                raise
            finally:
                root.set_attributes(session.totals)
                labels = {'gen_ai.request.model': config.model, 'agent.intent': session.intent, 'outcome': outcome}
                runtime.requests.add(1, labels)
                runtime.duration.record(time.perf_counter() - started, labels)
                _session.reset(token)
    finally:
        release_runtime(runtime)


@contextmanager
def agent_span(name, attributes=None):
    session = _session.get()
    if not session or not session.span:
        yield None
        return
    with session.runtime.tracer.start_as_current_span(
        name, attributes={k: v for k, v in (attributes or {}).items() if k in SAFE_ATTRIBUTES},
        record_exception=False, set_status_on_exception=False,
    ) as span:
        try:
            yield span
            span.set_status(Status(StatusCode.OK))
        except Exception as exc:
            span.set_attribute('error.type', type(exc).__name__)
            span.set_status(Status(StatusCode.ERROR))
            raise


def retrieval_hits(count):
    session = _session.get()
    if session and session.span:
        with session.lock:
            session.totals['agent.retrieval.hits'] += count


def rerank_observation(duration, model, candidates, status, reason):
    session = _session.get()
    if not session or not session.span:
        return
    with session.lock:
        for key, value in [('agent.rerank.calls', 1), ('agent.rerank.fallbacks', int(status == 'fallback')),
                           ('agent.rerank.failures', int(status in ('failed', 'fallback')))]:
            session.totals[key] = session.totals.get(key, 0) + value
    labels = {'agent.rerank.model': model, 'outcome': status, 'reason': reason}
    session.runtime.rerank_calls.add(1, labels)
    session.runtime.rerank_duration.record(duration, labels)
    session.runtime.rerank_candidates.record(candidates, {'agent.rerank.model': model})


class ModelTelemetry(BaseCallbackHandler):
    """Measure LLM operations without inspecting/recording prompts or model output text."""

    def __init__(self, session):
        self.session = session
        self.pending = {}
        self.lock = threading.Lock()

    def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        span = self.session.runtime.tracer.start_span(
            'chat.deepseek', kind=SpanKind.CLIENT,
            attributes={'gen_ai.operation.name': 'chat', 'gen_ai.provider.name': 'deepseek',
                        'gen_ai.request.model': self.session.config.model},
        )
        with self.lock:
            self.pending[run_id] = (span, time.perf_counter())
        with self.session.lock:
            self.session.totals['agent.llm.calls'] += 1

    def on_llm_end(self, response, *, run_id, **kwargs):
        usage = {}
        if response.generations and response.generations[0]:
            message = getattr(response.generations[0][0], 'message', None)
            usage = getattr(message, 'usage_metadata', None) or {}
        fallback = (response.llm_output or {}).get('token_usage', {})
        tokens = {'input': usage.get('input_tokens', fallback.get('prompt_tokens', 0)),
                  'output': usage.get('output_tokens', fallback.get('completion_tokens', 0))}
        self._finish(run_id, tokens=tokens, response_model=(response.llm_output or {}).get('model_name'))

    def on_llm_error(self, error, *, run_id, **kwargs):
        self._finish(run_id, error=error)

    def _finish(self, run_id, tokens=None, response_model=None, error=None):
        with self.lock:
            pending = self.pending.pop(run_id, None)
        if pending is None:
            return
        span, started = pending
        labels = {'gen_ai.request.model': self.session.config.model, 'gen_ai.operation.name': 'chat'}
        if error is not None:
            span.set_attribute('error.type', type(error).__name__)
            span.set_status(Status(StatusCode.ERROR))
        else:
            span.set_status(Status(StatusCode.OK))
            if isinstance(response_model, str):
                span.set_attribute('gen_ai.response.model', response_model[:100])
            for kind, value in (tokens or {}).items():
                value = value if type(value) is int and value >= 0 else 0
                key = 'gen_ai.usage.' + kind + '_tokens'
                span.set_attribute(key, value)
                with self.session.lock:
                    self.session.totals[key] += value
                self.session.runtime.tokens.add(value, dict(labels, **{'gen_ai.token.type': kind}))
        self.session.runtime.model_duration.record(time.perf_counter() - started, labels)
        span.end()
