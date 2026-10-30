"""Preloaded Django worker. A process is reusable; a DataSession never is."""
import json
import os
import sys

from django.core.management.base import BaseCommand
from django.db import connections

from support_ai.mcp_backend import DataSession, failure
from support_ai.mcp_security import AccessDenied, GRANT_ENV


class Command(BaseCommand):
    requires_system_checks = []
    requires_migrations_checks = False

    def handle(self, *args, **options):
        os.environ.pop(GRANT_ENV, None)
        session = None
        self.stdout.write('{"worker_ready":1}')
        self.stdout.flush()
        try:
            while True:
                line = sys.stdin.buffer.readline(262145)
                if not line:
                    return
                if len(line) > 262144:
                    return
                try:
                    request = json.loads(line)
                    action = request.get('action')
                    if action == 'open' and set(request) == {'action', 'grant'}:
                        if session is not None:
                            raise AccessDenied('Worker already leased')
                        session = DataSession(request['grant'])
                        result = {'session_ready': 1, 'expires_at': session.grant['expires_at']}
                    elif action == 'close' and set(request) == {'action'}:
                        session = None
                        connections.close_all()
                        result = {'session_closed': 1}
                    elif (action == 'call' and set(request) == {'action', 'tool', 'arguments'}
                          and session is not None):
                        result = session.invoke(request['tool'], request['arguments'])
                    else:
                        result = failure('INVALID_ARGUMENT')
                except AccessDenied:
                    result = failure('ACCESS_DENIED')
                except Exception:
                    result = failure('SERVICE_UNAVAILABLE')
                self.stdout.write(json.dumps(result, ensure_ascii=False, default=str, allow_nan=False))
                self.stdout.flush()
        finally:
            session = None
            connections.close_all()
