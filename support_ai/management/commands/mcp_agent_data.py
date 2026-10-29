"""Fixed, persistent backend for one MCP grant. stdout is JSON lines only."""
import json
import os
import sys

from django.core.management.base import BaseCommand

from support_ai.mcp_backend import DataSession, failure
from support_ai.mcp_security import GRANT_ENV, AccessDenied


class Command(BaseCommand):
    requires_system_checks = []
    requires_migrations_checks = False

    def handle(self, *args, **options):
        try:
            session = DataSession(os.environ.pop(GRANT_ENV, ''))
        except AccessDenied:
            self.stdout.write(json.dumps(failure('ACCESS_DENIED')))
            return
        self.stdout.write('{"backend_ready":1}')
        self.stdout.flush()
        while True:
            line = sys.stdin.buffer.readline(262145)
            if not line:
                return
            if len(line) > 262144:
                self.stdout.write(json.dumps(failure('INVALID_ARGUMENT')))
                return
            try:
                request = json.loads(line)
                if not isinstance(request, dict) or set(request) != {'tool', 'arguments', 'bridge_spans'}:
                    raise ValueError()
                result = session.invoke(request['tool'], request['arguments'], request['bridge_spans'])
            except Exception:
                result = failure('INVALID_ARGUMENT')
            self.stdout.write(json.dumps(result, ensure_ascii=False, default=str, allow_nan=False))
            self.stdout.flush()
