"""Content-free structured runtime logging; never serialize request or exception text."""
import json
import logging
import logging.config
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import re
import sys
from contextvars import ContextVar
from datetime import datetime, timezone


request_context = ContextVar('tea_saas_http_log_context', default=None)
EVENTS = frozenset({
    'http.request.completed', 'application.log', 'runtime.log.failed', 'runtime.warning',
    'users.registration.succeeded', 'users.registration.failed', 'users.login.succeeded',
    'users.login.failed',
    'orders.receipt.requested', 'orders.receipt.invalid_json', 'orders.receipt.validated',
    'orders.receipt.not_found', 'orders.delete.failed',
    'support.storage.failed', 'support.workflow.failed', 'support.planning.unavailable',
    'support.query_rewrite.unavailable', 'support.query_route.unavailable',
    'support.retrieval.unavailable', 'support.telemetry.persistence_failed',
})
IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_.-]{0,119}$')
HEX32 = re.compile(r'^[0-9a-f]{32}$')
HEX16 = re.compile(r'^[0-9a-f]{16}$')


def update_request_context(**values):
    current = request_context.get()
    if current is not None:
        request_context.set(dict(current, **values))


def bind_agent_trace(trace_id, span_id):
    """Keep the current execution's root trace for the HTTP completion event."""
    if HEX32.fullmatch(trace_id or '') and HEX16.fullmatch(span_id or ''):
        update_request_context(trace_id=trace_id, span_id=span_id)


def safe_name(value, fallback='unknown'):
    return value if isinstance(value, str) and IDENTIFIER.fullmatch(value) else fallback


def structured_record(record):
    # No getMessage(), args, extra dictionaries, request, response body, exc text or locals.
    # A positive event allowlist also protects against arbitrary third-party log strings.
    data = {
        'timestamp': datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec='milliseconds'),
        'level': logging.getLevelName(record.levelno) if record.levelno in (10, 20, 30, 40, 50) else 'INFO',
        'service': 'tea_saas', 'logger': safe_name(record.name, 'external'),
        'event': record.msg if isinstance(record.msg, str) and record.msg in EVENTS else 'application.log',
    }
    if record.name == 'py.warnings':
        data['event'] = 'runtime.warning'
    context = request_context.get()
    if context is None:
        # Django may report a response status after the outer middleware has returned.
        context = getattr(getattr(record, 'request', None), '_runtime_log_context', {})
    for key, pattern in (('http_request_id', HEX32), ('trace_id', HEX32), ('span_id', HEX16)):
        value = context.get(key, '')
        if isinstance(value, str) and pattern.fullmatch(value):
            data[key] = value
    # OpenTelemetry is optional for core logging. Prefer an active child span when present.
    try:
        from opentelemetry.trace import get_current_span
        span = get_current_span().get_span_context()
        if span.is_valid:
            data.update(trace_id=format(span.trace_id, '032x'), span_id=format(span.span_id, '016x'))
    except Exception:
        pass
    method = context.get('method')
    if method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'TRACE', 'OTHER'):
        data['method'] = method
    if isinstance(context.get('route'), str):
        data['route'] = context['route'][:240]
    for key in ('http_status', 'business_code'):
        if type(context.get(key)) is int:
            data[key] = context[key]
    duration = context.get('duration_ms')
    if type(duration) in (int, float) and 0 <= duration < 1e12:
        data['duration_ms'] = round(duration, 2)
    if context.get('outcome') in ('success', 'business_error', 'client_error', 'server_error'):
        data['outcome'] = context['outcome']
    error_type = getattr(record, 'error_type', None) or context.get('error_type')
    if error_type:
        data['error_type'] = safe_name(error_type)
    if record.exc_info and record.exc_info[0]:
        data['error_type'] = safe_name(record.exc_info[0].__name__)
        frames = []
        tb = record.exc_info[2]
        while tb is not None:
            code = tb.tb_frame.f_code
            frames.append({'file': safe_name(Path(code.co_filename).name),
                           'function': safe_name(code.co_name), 'line': tb.tb_lineno})
            tb = tb.tb_next
        data['stack'] = frames[-30:]
    return data


class JsonFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(structured_record(record), ensure_ascii=False, allow_nan=False)


class TextFormatter(logging.Formatter):
    def format(self, record):
        data = structured_record(record)
        return ' '.join('{}={}'.format(key, json.dumps(value, ensure_ascii=False)) for key, value in data.items())


def report_output_failure():
    # Fixed fallback only: no original record, exception, path or recursive logger calls.
    try:
        sys.stderr.write('{"level":"WARNING","event":"runtime.log.failed","service":"tea_saas"}\n')
    except Exception:
        pass


class SafeStreamHandler(logging.StreamHandler):
    def handleError(self, record):
        report_output_failure()


class FrameworkDuplicateFilter(logging.Filter):
    def filter(self, record):
        # The middleware already emitted the HTTP completion. Keep actual exception stacks.
        return not (record.name == 'django.request' and not record.exc_info and
                    getattr(getattr(record, 'request', None), '_runtime_log_completed', False))


class SafeRotatingFileHandler(RotatingFileHandler):
    """Opt-in for a single local process. A failed disk sink never disables console."""
    def __init__(self, filename, maxBytes=10485760, backupCount=5):
        super().__init__(filename, maxBytes=maxBytes, backupCount=backupCount,
                         encoding='utf-8', delay=True)
        self.unavailable = False

    def emit(self, record):
        if self.unavailable:
            return
        try:
            Path(self.baseFilename).parent.mkdir(parents=True, exist_ok=True)
            super().emit(record)
        except Exception:
            self.handleError(record)

    def handleError(self, record):
        if not self.unavailable:
            report_output_failure()
        self.unavailable = True


def positive_int(value, default, maximum):
    try:
        number = int(value)
        return number if 1 <= number <= maximum else default
    except (ValueError, TypeError):
        return default


def build_logging_config(base_dir, environ=None):
    environ = os.environ if environ is None else environ
    level = environ.get('LOG_LEVEL', 'INFO').upper()
    if level not in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
        level = 'INFO'
    formatter = 'text' if environ.get('LOG_FORMAT', 'json').lower() == 'text' else 'json'
    handlers = {'console': {'class': 'tea_saas.runtime_logging.SafeStreamHandler',
                           'formatter': formatter, 'filters': ['framework_duplicates']}}
    if environ.get('LOG_TO_FILE', 'false').lower() == 'true':
        directory = Path(environ.get('LOG_DIR') or Path(base_dir) / 'logs')
        if not directory.is_absolute():
            directory = Path(base_dir) / directory
        handlers['file'] = {
            'class': 'tea_saas.runtime_logging.SafeRotatingFileHandler', 'formatter': formatter,
            'filters': ['framework_duplicates'],
            'filename': str(directory / 'application.log'),
            'maxBytes': positive_int(environ.get('LOG_MAX_BYTES'), 10485760, 1073741824),
            'backupCount': positive_int(environ.get('LOG_BACKUP_COUNT'), 5, 100),
        }
    loggers = {name: {'handlers': [], 'level': chosen, 'propagate': True} for name, chosen in (
        ('django', level), ('django.request', 'WARNING'), ('django.server', 'ERROR'),
        ('django.db.backends', 'ERROR'), ('httpx', 'WARNING'), ('httpcore', 'WARNING'),
        ('openai', 'WARNING'), ('urllib3', 'WARNING'),
    )}
    return {'version': 1, 'disable_existing_loggers': False,
            'filters': {'framework_duplicates': {'()': 'tea_saas.runtime_logging.FrameworkDuplicateFilter'}},
            'formatters': {'json': {'()': 'tea_saas.runtime_logging.JsonFormatter'},
                           'text': {'()': 'tea_saas.runtime_logging.TextFormatter'}},
            'handlers': handlers, 'root': {'handlers': list(handlers), 'level': level}, 'loggers': loggers}


def configure_logging(config):
    logging.config.dictConfig(config)
    logging.captureWarnings(True)
