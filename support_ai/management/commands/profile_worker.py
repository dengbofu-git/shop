import json
import time
from collections import Counter
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections


class Command(BaseCommand):
    help = 'Process durable account preference updates and reconcile completed purchases.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--poll-seconds', type=int, default=30)
        parser.add_argument('--batch-size', type=int, default=20)
        parser.add_argument('--retry-dead', help='Explicitly requeue one repaired dead job by UUID')

    def handle(self, *args, **options):
        if not settings.SUPPORT_AUTO_PROFILE_ENABLED:
            raise CommandError('Automatic account preferences are disabled; apply schema and authorize activation first.')
        if not 1 <= options['poll_seconds'] <= 60 or not 1 <= options['batch_size'] <= 100:
            raise CommandError('poll-seconds must be 1..60 and batch-size must be 1..100')
        from support_ai.profile_worker import process_next
        if options['retry_dead']:
            from support_ai.profile_worker import retry_dead_job
            try:
                changed = retry_dead_job(options['retry_dead'])
            except (ValueError, TypeError):
                raise CommandError('A valid dead-job UUID is required') from None
            if not changed:
                raise CommandError('No dead job was requeued')
            self.stdout.write(json.dumps({'status': 'requeued'}))
            return
        from support_ai.profile_behavior import reconcile_behavior_batch
        cursor = 0
        while True:
            close_old_connections()
            scan = reconcile_behavior_batch(after_owner_id=cursor, limit=options['batch_size'])
            cursor = 0 if scan['complete'] else scan['cursor']
            processed = 0
            for _ in range(options['batch_size']):
                result = process_next()
                if result['status'] in ('idle', 'disabled'):
                    break
                processed += 1
            self.stdout.write(json.dumps({'processed': processed, 'scan_processed': scan['processed'],
                                          'scan_complete': scan['complete'],
                                          'skipped_codes': dict(Counter(x['code'] for x in scan.get('skipped', [])))}))
            if options['once']:
                break
            time.sleep(options['poll_seconds'])
