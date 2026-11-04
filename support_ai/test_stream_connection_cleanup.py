"""Worker connections must end with the stream, regardless of GC timing."""
import time
from threading import Event
from types import SimpleNamespace
from unittest import skipUnless

from django.db import connection, connections
from django.http import JsonResponse
from django.test import TransactionTestCase

from .streaming import StreamCancelled, event_response


@skipUnless(connection.vendor == 'postgresql', 'Requires isolated PostgreSQL sessions')
class StreamConnectionCleanupTests(TransactionTestCase):
    def backend_pid(self):
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_backend_pid()')
            return cursor.fetchone()[0]

    def exercise(self, outcome):
        main_pid = self.backend_pid()
        # A strong reference prevents garbage collection from hiding the leak.
        held = []

        def run():
            worker = connections['default']
            with worker.cursor() as cursor:
                cursor.execute('SELECT pg_backend_pid()')
                pid = cursor.fetchone()[0]
            self.assertGreater(worker.settings_dict['CONN_MAX_AGE'], 0)
            held.append((worker, pid))
            if outcome == 'error':
                raise RuntimeError('Synthetic workflow failure')
            if outcome == 'cancel':
                raise StreamCancelled('Synthetic disconnect')
            return JsonResponse({'answer': 'Synthetic answer'})

        response = event_response(SimpleNamespace(), run)
        try:
            frames = list(response.streaming_content)
            self.assertTrue(frames)
            self.assertEqual(len(held), 1)
            worker, pid = held[0]
            self.assertNotEqual(pid, main_pid)
            self.assertIsNone(worker.connection, 'A finished stream retained its fresh PostgreSQL connection')
            self.assertEqual(self.backend_pid(), main_pid, 'Worker cleanup closed the caller connection')
            deadline = time.monotonic() + 2
            while True:
                with connection.cursor() as cursor:
                    cursor.execute('SELECT count(*) FROM pg_stat_activity WHERE pid=%s', [pid])
                    remaining = cursor.fetchone()[0]
                if not remaining:
                    break
                self.assertLess(time.monotonic(), deadline, 'Worker PostgreSQL session remained alive')
                Event().wait(.01)
        finally:
            response.close()
            # The RED test must also leave its disposable database clean.
            for worker, _ in held:
                if worker.connection is not None:
                    worker.inc_thread_sharing()
                    try:
                        worker.close()
                    finally:
                        worker.dec_thread_sharing()

    def test_success_closes_its_session_without_closing_the_caller(self):
        self.exercise('success')

    def test_error_closes_its_session_without_closing_the_caller(self):
        self.exercise('error')

    def test_cancellation_closes_its_session_without_closing_the_caller(self):
        self.exercise('cancel')
