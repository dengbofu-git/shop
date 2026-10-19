"""Privacy, output failure, rotation and request isolation checks with synthetic data."""
import io
import json
import logging
import logging.config
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path
import sys
import tempfile
import threading
import warnings
from types import SimpleNamespace
from unittest.mock import patch

from django.http import JsonResponse, StreamingHttpResponse
from django.test import AsyncClient, Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import path
from users import views as user_views
from orders import views as order_views

from tea_saas.request_logging import RequestLoggingMiddleware
from tea_saas.runtime_logging import (JsonFormatter, TextFormatter, SafeStreamHandler,
    SafeRotatingFileHandler, FrameworkDuplicateFilter, bind_agent_trace, build_logging_config, request_context, structured_record)


SECRETS = ('password-unlabelled-xyz', 'Bearer synthetic-private-token', 'buyer@example.test',
           '13800138000', '6472', 'mysql://user:secret@internal/db', 'private prompt and answer')


def record(message='application.log', args=(), exc_info=None):
    return logging.LogRecord('synthetic.module', logging.ERROR, __file__, 30, message, args, exc_info)


@contextmanager
def captured_root():
    stream = io.StringIO()
    handler = SafeStreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    with patch.object(root, 'handlers', [handler]), patch.object(root, 'level', logging.INFO):
        yield stream


def completed(stream):
    return [row for row in map(json.loads, stream.getvalue().splitlines()) if row['event'] == 'http.request.completed']


def ok_view(request, username=None):
    logging.getLogger('synthetic.view').info('application.log')
    return JsonResponse({'code': 200, 'secret': SECRETS[0]})


def failed_view(request):
    raise RuntimeError(' '.join(SECRETS))


def business_view(request):
    return JsonResponse({'code': 10005, 'error': ' '.join(SECRETS)})


def large_view(request):
    return JsonResponse({'code': 10005, 'data': 'x' * 65536})


def stream_view(request):
    def body():
        raise AssertionError('The logging middleware must not consume streaming content')
        yield b''
    return StreamingHttpResponse(body(), content_type='application/json')


urlpatterns = [path('ok/<str:username>', ok_view), path('business', business_view),
               path('failed', failed_view), path('large', large_view), path('stream', stream_view),
               path('login', user_views.login),
               path('register', user_views.register),
               path('receipt/<str:username>', order_views.OrdersView.as_view())]


class FormatterTests(SimpleTestCase):
    def tearDown(self):
        self.assertIsNone(request_context.get())

    def test_raw_message_args_extras_cached_traceback_and_pii_never_serialize(self):
        try:
            raise RuntimeError(' '.join(SECRETS))
        except RuntimeError:
            entry = record(' '.join(SECRETS), exc_info=sys.exc_info())
        entry.exc_text = ' '.join(SECRETS)
        entry.password = SECRETS[0]
        entry.request = {'headers': {'Authorization': SECRETS[1]}}
        for formatter in (JsonFormatter(), TextFormatter()):
            text = formatter.format(entry)
            for value in SECRETS:
                self.assertNotIn(value, text)
        data = json.loads(JsonFormatter().format(entry))
        self.assertEqual(data['error_type'], 'RuntimeError')
        self.assertTrue(data['stack'])
        self.assertEqual(set(data['stack'][0]), {'file', 'line', 'function'})
        self.assertEqual(data['event'], 'application.log')

    def test_formatters_never_call_string_conversion_on_arguments(self):
        class Dangerous:
            def __str__(self):
                raise AssertionError('Do not inspect arbitrary arguments')
        data = structured_record(record('secret %s', (Dangerous(),)))
        self.assertEqual(data['event'], 'application.log')

    def test_python_warnings_do_not_bypass_safe_formatting(self):
        with captured_root() as output, warnings.catch_warnings():
            warnings.simplefilter('always')
            warnings.warn(SECRETS[0], RuntimeWarning)
        rows = list(map(json.loads, output.getvalue().splitlines()))
        self.assertEqual(rows[0]['event'], 'runtime.warning')
        self.assertNotIn(SECRETS[0], output.getvalue())

    def test_only_registered_events_and_identifiers_are_emitted(self):
        entry = record('users.login.failed')
        token = request_context.set({'http_request_id': 'a' * 32, 'trace_id': SECRETS[0], 'method': 'POST',
                                     'business_code': True, 'password': SECRETS[0]})
        try:
            data = structured_record(entry)
            self.assertEqual(data['event'], 'users.login.failed')
            self.assertEqual(data['http_request_id'], 'a' * 32)
            self.assertNotIn('trace_id', data)
            self.assertNotIn('business_code', data)
            self.assertNotIn('password', data)
        finally:
            request_context.reset(token)

    def test_defaults_and_invalid_configuration_are_safe(self):
        for env in ({}, {'LOG_LEVEL': 'invalid', 'LOG_FORMAT': 'invalid'}):
            config = build_logging_config(Path.cwd(), env)
            self.assertEqual(list(config['handlers']), ['console'])
            self.assertEqual(config['root']['level'], 'INFO')
            self.assertEqual(config['handlers']['console']['formatter'], 'json')
            self.assertFalse(config['disable_existing_loggers'])
            self.assertEqual(config['loggers']['django.db.backends']['level'], 'ERROR')
        config = build_logging_config(Path.cwd(), {'LOG_TO_FILE': 'true', 'LOG_FORMAT': 'text',
                                    'LOG_MAX_BYTES': 'bad', 'LOG_BACKUP_COUNT': '-1'})
        self.assertEqual(config['handlers']['file']['maxBytes'], 10485760)
        self.assertEqual(config['handlers']['file']['backupCount'], 5)
        self.assertEqual(config['handlers']['console']['formatter'], 'text')

    def test_stream_formatter_failure_uses_fixed_fallback(self):
        output = io.StringIO()
        handler = SafeStreamHandler(output)
        formatter = JsonFormatter()
        handler.setFormatter(formatter)
        with patch.object(formatter, 'format', side_effect=ValueError(SECRETS[0])), patch('sys.stderr', output):
            handler.handle(record(SECRETS[0]))
        self.assertEqual(json.loads(output.getvalue())['event'], 'runtime.log.failed')
        self.assertNotIn(SECRETS[0], output.getvalue())

    def test_framework_duplicate_filter_preserves_exception_records(self):
        duplicate = record('raw response body')
        duplicate.name = 'django.request'
        duplicate.request = SimpleNamespace(_runtime_log_completed=True,
                                            _runtime_log_context={'http_request_id': 'e' * 32})
        self.assertFalse(FrameworkDuplicateFilter().filter(duplicate))
        self.assertEqual(structured_record(duplicate)['http_request_id'], 'e' * 32)
        duplicate.exc_info = (RuntimeError, RuntimeError(SECRETS[0]), None)
        self.assertTrue(FrameworkDuplicateFilter().filter(duplicate))

    def test_file_failure_preserves_console_and_warns_only_once(self):
        with tempfile.TemporaryDirectory(prefix='tea_saas-log-test-') as folder:
            blocker = Path(folder) / 'not-a-directory'
            blocker.write_text('synthetic', encoding='utf-8')
            output = io.StringIO()
            console = SafeStreamHandler(output)
            console.setFormatter(JsonFormatter())
            file_handler = SafeRotatingFileHandler(str(blocker / 'application.log'))
            file_handler.setFormatter(JsonFormatter())
            try:
                with patch('sys.stderr', output):
                    for _ in range(2):
                        console.handle(record('users.login.succeeded'))
                        file_handler.handle(record('users.login.succeeded'))
                rows = list(map(json.loads, output.getvalue().splitlines()))
                self.assertEqual(sum(row['event'] == 'users.login.succeeded' for row in rows), 2)
                self.assertEqual(sum(row['event'] == 'runtime.log.failed' for row in rows), 1)
            finally:
                file_handler.close()

    def test_file_rotation_limits_backups(self):
        with tempfile.TemporaryDirectory(prefix='tea_saas-log-test-') as folder:
            target = Path(folder) / 'application.log'
            handler = SafeRotatingFileHandler(str(target), maxBytes=500, backupCount=2)
            handler.setFormatter(JsonFormatter())
            try:
                for _ in range(20):
                    handler.handle(record('users.login.failed'))
            finally:
                handler.close()
            self.assertEqual(len(list(Path(folder).glob('application.log*'))), 3)
            self.assertLessEqual(target.stat().st_size, 500)


@override_settings(ROOT_URLCONF=__name__, DEBUG=False)
class RequestLoggingTests(SimpleTestCase):
    def tearDown(self):
        self.assertIsNone(request_context.get())

    def test_route_template_and_server_generated_id_without_body_or_headers(self):
        with captured_root() as stream:
            response = self.client.post('/ok/private-account?token=private-query', data=json.dumps({'password': SECRETS[0]}),
                                        content_type='application/json', HTTP_X_REQUEST_ID='b' * 32,
                                        HTTP_AUTHORIZATION=SECRETS[1], HTTP_COOKIE=SECRETS[0])
        rows = completed(stream)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['http_request_id'], response['X-Request-ID'])
        self.assertNotEqual(row['http_request_id'], 'b' * 32)
        self.assertEqual(len(row['http_request_id']), 32)
        self.assertEqual(row['route'], 'ok/<str:username>')
        self.assertEqual(row['business_code'], 200)
        self.assertEqual(row['outcome'], 'success')
        for value in (*SECRETS, 'private-account', 'private-query'):
            self.assertNotIn(value, stream.getvalue())

    def test_http_200_business_failure_is_not_counted_as_success(self):
        with captured_root() as stream:
            response = self.client.get('/business')
        row = completed(stream)[0]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(row['http_status'], 200)
        self.assertEqual(row['business_code'], 10005)
        self.assertEqual(row['outcome'], 'business_error')

    def test_unhandled_exception_stack_is_recorded_once_and_context_is_cleared(self):
        with captured_root() as stream:
            response = Client(raise_request_exception=False).get('/failed')
        rows = list(map(json.loads, stream.getvalue().splitlines()))
        stacks = [row for row in rows if row.get('stack')]
        self.assertEqual(response.status_code, 500)
        self.assertEqual(len(stacks), 1)
        self.assertEqual(stacks[0]['error_type'], 'RuntimeError')
        self.assertEqual(stacks[0]['http_request_id'], response['X-Request-ID'])
        self.assertEqual(completed(stream)[0]['outcome'], 'server_error')
        for secret in SECRETS:
            self.assertNotIn(secret, stream.getvalue())

    def test_404_does_not_log_raw_path(self):
        with captured_root() as stream:
            response = self.client.get('/unknown/private-account')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(completed(stream)[0]['route'], '<unresolved>')
        self.assertNotIn('private-account', stream.getvalue())
        for row in map(json.loads, stream.getvalue().splitlines()):
            self.assertEqual(row['http_request_id'], response['X-Request-ID'])

    def test_streaming_is_not_consumed_and_large_json_is_not_parsed(self):
        with captured_root() as stream:
            response = self.client.get('/stream')
            response.close()
            self.client.get('/large')
        rows = completed(stream)
        self.assertEqual(len(rows), 2)
        self.assertTrue(all('business_code' not in row for row in rows))

    def test_parallel_requests_do_not_share_identifiers(self):
        barrier = threading.Barrier(2)
        def process(_):
            def view(request):
                barrier.wait(timeout=10)
                logging.getLogger('synthetic.parallel').info('application.log')
                return JsonResponse({'code': 200})
            response = RequestLoggingMiddleware(view)(RequestFactory().get('/ignored'))
            self.assertIsNone(request_context.get())
            return response['X-Request-ID']
        with captured_root() as stream, ThreadPoolExecutor(max_workers=2) as pool:
            identifiers = list(pool.map(process, range(2)))
        self.assertEqual(len(set(identifiers)), 2)
        rows = list(map(json.loads, stream.getvalue().splitlines()))
        for identifier in identifiers:
            group = [row for row in rows if row.get('http_request_id') == identifier]
            self.assertEqual(len(group), 2)

    def test_trace_survives_until_completion_but_not_the_next_request(self):
        def view(request):
            bind_agent_trace('c' * 32, 'd' * 16)
            return JsonResponse({'code': 200})
        with captured_root() as stream:
            RequestLoggingMiddleware(view)(RequestFactory().get('/ignored'))
            self.client.get('/ok/another')
        first, second = completed(stream)
        self.assertEqual(first['trace_id'], 'c' * 32)
        self.assertNotIn('trace_id', second)

    def test_real_agent_root_and_child_spans_correlate_with_http_logs(self):
        from support_ai.telemetry import observe_agent, agent_span, shutdown_telemetry
        from opentelemetry.sdk.trace.export import SpanExportResult
        configuration = SimpleNamespace(telemetry_enabled=True, export_enabled=False,
                                        otlp_endpoint='http://127.0.0.1:4318', model='synthetic', revision=0)
        seen = {}
        def view(request):
            with observe_agent(configuration) as observation:
                seen['root'] = observation.trace_id
                with agent_span('agent.synthetic') as span:
                    seen['child'] = format(span.get_span_context().span_id, '016x')
                    logging.getLogger('synthetic.agent').info('application.log')
            # A replay response's trace field must not establish a new execution trace.
            return JsonResponse({'trace_id': observation.trace_id})
        try:
            with patch('support_ai.telemetry.DatabaseSpanExporter.export', return_value=SpanExportResult.SUCCESS):
                with captured_root() as stream:
                    response = RequestLoggingMiddleware(view)(RequestFactory().get('/ignored'))
                    self.client.get('/ok/synthetic')
            rows = list(map(json.loads, stream.getvalue().splitlines()))
            child = next(row for row in rows if row['logger'] == 'synthetic.agent')
            first, second = completed(stream)
            self.assertEqual(child['trace_id'], seen['root'])
            self.assertEqual(child['span_id'], seen['child'])
            self.assertEqual(child['http_request_id'], response['X-Request-ID'])
            self.assertEqual(first['trace_id'], seen['root'])
            self.assertNotIn('trace_id', second)
        finally:
            shutdown_telemetry()

    def test_login_exception_keeps_business_response_but_not_exception_text_in_logs(self):
        with captured_root() as stream, patch('users.views.UserProfile.objects.get', side_effect=RuntimeError(SECRETS[0])):
            response = self.client.post('/login', data=json.dumps({'username': 'synthetic-user', 'password': SECRETS[0]}),
                                        content_type='application/json')
        self.assertEqual(response.json()['code'], 10005)
        self.assertEqual(completed(stream)[0]['business_code'], 10005)
        self.assertNotIn(SECRETS[0], stream.getvalue())
        self.assertNotIn('synthetic-user', stream.getvalue())
        self.assertIn('users.login.failed', stream.getvalue())

    def test_registration_success_does_not_print_identity_fields(self):
        with captured_root() as stream, patch('sys.stdout', new_callable=io.StringIO) as stdout, patch(
                'users.views.UserProfile.objects.get', side_effect=user_views.UserProfile.DoesNotExist), patch(
                'users.views.UserProfile.objects.create') as create, patch('users.views.UserProfile.objects.filter'), patch(
                'users.views.jwt_encode', return_value='synthetic-token'):
            create.return_value.pk = 1
            response = self.client.post('/register', data=json.dumps({'uname': 'testbuyer', 'password': 'test-123',
                          'phone': SECRETS[3], 'email': SECRETS[2]}), content_type='application/json')
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(stdout.getvalue(), '')
        self.assertIn('users.registration.succeeded', stream.getvalue())
        for value in ('testbuyer', 'test-123', SECRETS[2], SECRETS[3], 'synthetic-token'):
            self.assertNotIn(value, stream.getvalue())

    def test_receipt_invalid_json_does_not_log_raw_body_or_account_path(self):
        with captured_root() as stream, patch('orders.views.jwt_decode', return_value={'id': 1}), patch(
                'orders.views.UserProfile.objects.get', return_value=SimpleNamespace(username='synthetic-account')), patch(
                'orders.views.get_redis_connection'):
            response = self.client.put('/receipt/synthetic-account', data='{"password":"'+SECRETS[0]+'"',
                                       content_type='application/json', HTTP_AUTHORIZATION=SECRETS[1])
        self.assertEqual(response.status_code, 400)
        self.assertIn('orders.receipt.invalid_json', stream.getvalue())
        for value in (SECRETS[0], SECRETS[1], 'synthetic-account'):
            self.assertNotIn(value, stream.getvalue())

    def test_escaped_exception_re_raises_without_leaking_context(self):
        with captured_root() as stream, self.assertRaises(RuntimeError):
            RequestLoggingMiddleware(failed_view)(RequestFactory().get('/ignored'))
        self.assertEqual(completed(stream)[0]['error_type'], 'RuntimeError')

    def test_log_directory_failure_does_not_change_http_response(self):
        with tempfile.TemporaryDirectory(prefix='tea_saas-log-test-') as folder:
            blocker = Path(folder) / 'blocked'
            blocker.write_text('synthetic', encoding='utf-8')
            handler = SafeRotatingFileHandler(str(blocker / 'application.log'))
            handler.setFormatter(JsonFormatter())
            try:
                with captured_root() as stream:
                    logging.getLogger().addHandler(handler)
                    with patch('sys.stderr', stream):
                        response = self.client.get('/ok/synthetic')
                self.assertEqual(response.json()['code'], 200)
                self.assertTrue(response['X-Request-ID'])
                self.assertEqual(completed(stream)[0]['outcome'], 'success')
            finally:
                handler.close()

    async def test_asgi_adaptation_keeps_request_context(self):
        with captured_root() as stream:
            response = await AsyncClient().get('/ok/synthetic')
        self.assertEqual(completed(stream)[0]['http_request_id'], response['X-Request-ID'])
