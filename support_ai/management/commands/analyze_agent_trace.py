"""Read a stored trace and emit content-free timing analysis; no model calls."""
import json
import re

from django.core.management.base import BaseCommand, CommandError

from support_ai.models import AgentSpan
from support_ai.trace_analysis import analyze_spans


class Command(BaseCommand):
    requires_system_checks=[]

    def add_arguments(self,parser):
        parser.add_argument('trace_id')

    def handle(self,*args,**options):
        identifier=options['trace_id']
        if not re.fullmatch(r'[0-9a-f]{32}',identifier):
            raise CommandError('Invalid trace id')
        rows=list(AgentSpan.objects.filter(trace_id=identifier).values(
            'span_id','parent_span_id','name','started_at','duration_ms','status','attributes'))
        try:
            result=analyze_spans(rows)
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(json.dumps(dict(trace_id=identifier,**result),ensure_ascii=False,indent=2))
