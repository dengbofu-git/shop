"""One completion event per HTTP request, independent of Agent idempotency keys."""
import json
import logging
import time
import uuid

from .runtime_logging import request_context, update_request_context


logger = logging.getLogger(__name__)


class RequestLoggingMiddleware:
    # Django adapts this synchronous middleware for the existing ASGI entrypoint.
    sync_capable = True
    async_capable = False

    def __init__(self, get_response):
        self.get_response = get_response

    def process_view(self, request, view_func, view_args, view_kwargs):
        match = request.resolver_match
        update_request_context(route=getattr(match, 'route', None) or '<unresolved>')

    def process_exception(self, request, exception):
        update_request_context(error_type=type(exception).__name__)
        # Django logs unhandled exceptions once, while this context is still active.
        return None

    def __call__(self, request):
        request_id = uuid.uuid4().hex
        request.http_request_id = request_id
        method = request.method if request.method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS', 'TRACE') else 'OTHER'
        token = request_context.set({'http_request_id': request_id, 'method': method, 'route': '<unresolved>'})
        started = time.perf_counter()
        try:
            try:
                response = self.get_response(request)
            except Exception:
                update_request_context(http_status=500, outcome='server_error',
                                       duration_ms=(time.perf_counter() - started) * 1000)
                logger.exception('http.request.completed')
                raise
            response['X-Request-ID'] = request_id
            if response.streaming:
                self._defer_stream_log(request, response, started)
                return response
            values = {'http_status': response.status_code, 'duration_ms': (time.perf_counter() - started) * 1000}
            # Inspect only a bounded, already-built JSON envelope, never streaming bodies.
            # Only an integer code survives; no response content is passed to logging.
            if not response.streaming and response.get('Content-Type', '').split(';')[0] == 'application/json':
                body = response.content
                if len(body) <= 65536:
                    try:
                        payload = json.loads(body)
                        if isinstance(payload, dict) and type(payload.get('code')) is int:
                            values['business_code'] = payload['code']
                    except (ValueError, UnicodeError):
                        pass
            status = response.status_code
            values['outcome'] = ('server_error' if status >= 500 else 'client_error' if status >= 400
                                 else 'business_error' if values.get('business_code', 200) not in (0, 200) else 'success')
            update_request_context(**values)
            level = logging.ERROR if status >= 500 else logging.WARNING if values['outcome'] != 'success' else logging.INFO
            logger.log(level, 'http.request.completed')
            request._runtime_log_completed = True
            return response
        finally:
            request._runtime_log_context = dict(request_context.get() or {})
            request_context.reset(token)

    @staticmethod
    def _defer_stream_log(request, response, started):
        """WSGI streams complete after the middleware has returned headers."""
        context = dict(request_context.get() or {})
        original = response.streaming_content
        finished = False

        def complete(interrupted=False):
            nonlocal finished
            if finished:
                return
            finished = True
            token = request_context.set(dict(context))
            try:
                stream = getattr(request, '_support_stream_context', {})
                status = stream.get('http_status', response.status_code)
                values = dict(http_status=response.status_code,
                              duration_ms=(time.perf_counter() - started) * 1000)
                if stream.get('trace_id'):
                    values['trace_id'] = stream['trace_id']
                if stream.get('span_id'):
                    values['span_id'] = stream['span_id']
                if status != response.status_code:
                    values['business_code'] = status
                values['outcome'] = ('server_error' if status >= 500 else
                    'client_error' if status >= 400 or interrupted else 'success')
                update_request_context(**values)
                logger.log(logging.ERROR if status >= 500 else
                           logging.WARNING if values['outcome'] != 'success' else logging.INFO,
                           'http.request.completed')
                request._runtime_log_completed = True
                request._runtime_log_context = dict(request_context.get() or {})
            finally:
                request_context.reset(token)

        def body():
            exhausted = False
            try:
                yield from original
                exhausted = True
            finally:
                complete(interrupted=not exhausted)

        response.streaming_content = body()
        # Also cover a response closed before its first iteration. Do not read it.
        response._resource_closers.append(lambda: complete(interrupted=True))
