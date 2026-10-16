from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from support_ai.models import AgentSpan


class Command(BaseCommand):
    help = 'Delete Agent span projections older than the chosen retention period (default: 30 days).'

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=30)

    def handle(self, *args, **options):
        if not 1 <= options['days'] <= 3650:
            raise CommandError('--days must be between 1 and 3650')
        count, _ = AgentSpan.objects.filter(started_at__lt=timezone.now() - timedelta(days=options['days'])).delete()
        self.stdout.write(self.style.SUCCESS('Deleted {} old Agent spans.'.format(count)))
