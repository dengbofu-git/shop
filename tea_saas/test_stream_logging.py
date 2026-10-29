"""HTTP completion must include stream duration and the worker's root Trace."""
from django.http import StreamingHttpResponse
from django.test import RequestFactory, SimpleTestCase
from unittest.mock import patch

from .request_logging import RequestLoggingMiddleware
from .runtime_logging import request_context
from .test_runtime_logging import captured_root, completed


class StreamLoggingTests(SimpleTestCase):
    def test_completion_is_deferred_and_merges_worker_context(self):
        now = [10.0]
        def view(request):
            def chunks():
                yield b'first'
                request._support_stream_context = {'trace_id':'a'*32, 'http_status':503}
                now[0] = 13.0
                yield b'error'
            return StreamingHttpResponse(chunks(), content_type='text/event-stream')
        with captured_root() as output, patch('tea_saas.request_logging.time.perf_counter', side_effect=lambda:now[0]):
            response = RequestLoggingMiddleware(view)(RequestFactory().post('/v1/support/chat/'))
            self.assertEqual(completed(output), [])
            self.assertIsNone(request_context.get())
            stream = iter(response.streaming_content)
            self.assertEqual(next(stream), b'first')
            self.assertEqual(completed(output), [])
            self.assertEqual(list(stream), [b'error'])
            response.close()
        rows = completed(output)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['duration_ms'], 3000)
        self.assertEqual(rows[0]['trace_id'], 'a'*32)
        self.assertEqual(rows[0]['http_status'], 200)
        self.assertEqual(rows[0]['business_code'], 503)
        self.assertEqual(rows[0]['outcome'], 'server_error')
        self.assertIsNone(request_context.get())

    def test_close_without_consuming_logs_once(self):
        def body():
            raise AssertionError('Do not consume the body for logging')
            yield b''
        with captured_root() as output:
            response = RequestLoggingMiddleware(lambda r:StreamingHttpResponse(body()))(RequestFactory().get('/'))
            self.assertEqual(completed(output), [])
            response.close()
            response.close()
        self.assertEqual(len(completed(output)), 1)
        self.assertIsNone(request_context.get())
