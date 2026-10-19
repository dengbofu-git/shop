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
