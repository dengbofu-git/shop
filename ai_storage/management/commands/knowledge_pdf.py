"""Trusted management commands for PDF ingestion and publication."""
import json
import time
from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import close_old_connections
from ai_storage.pdf_pipeline import service


class Command(BaseCommand):
    help = 'Submit, inspect, retry, publish PDF knowledge; run a leased worker.'

    def add_arguments(self, parser):
        sub = parser.add_subparsers(dest='action', required=True)
        submit = sub.add_parser('submit')
        submit.add_argument('file')
        submit.add_argument('--actor-id', type=int, required=True)
        submit.add_argument('--title', required=True)
        submit.add_argument('--source-key', required=True)
        submit.add_argument('--visibility', choices=['public', 'private'], default='private')
        submit.add_argument('--owner-id', type=int)
        submit.add_argument('--languages', default='chi_sim+eng')
        submit.add_argument('--ocr-mode', choices=['auto', 'force'], default='auto')
        submit.add_argument('--vision-mode', choices=['off', 'auto', 'force'], default='off')
        submit.add_argument('--vision-task', action='append', choices=['ocr_text', 'table_extract', 'figure_describe'])
        submit.add_argument('--document-backend', choices=['legacy', 'paddleocr'], default='legacy')
        submit.add_argument('--document-mode', choices=['auto', 'force'], default='auto')
        for verb in ('inspect', 'retry', 'cancel', 'publish', 'withdraw'):
            command = sub.add_parser(verb)
            command.add_argument('job_id')
            command.add_argument('--actor-id', type=int, required=True)
            if verb == 'inspect':
                command.add_argument('--page', type=int)
                command.add_argument('--chunk', type=int)
                command.add_argument('--limit', type=int, default=20)
            if verb == 'publish':
                command.add_argument('--accept-warnings', action='store_true')
        worker = sub.add_parser('worker')
        worker.add_argument('--once', action='store_true')
        worker.add_argument('--job-id')
        worker.add_argument('--poll-seconds', type=int, default=5)

    def handle(self, *args, **options):
        action = options['action']
        try:
            if action == 'worker':
                if not 1 <= options['poll_seconds'] <= 60:
                    raise ValueError('Poll interval must be 1 to 60 seconds')
                while True:
                    close_old_connections()
                    job = service.claim(options.get('job_id'))
                    if job:
                        service.process(job)
                        state = service.preview_worker(job.pk)
                        self.stdout.write(json.dumps(state))
                        if state['status'] == 'failed' and (options['once'] or options.get('job_id')):
                            raise CommandError('PDF import failed; use inspect to review the fixed error code')
                    elif options.get('job_id'):
                        raise CommandError('No runnable job with this identifier')
                    if options['once'] or options.get('job_id'):
                        break
                    time.sleep(options['poll_seconds'])
                return
            if action == 'submit':
                job = service.enqueue(options['file'], options['actor_id'], options['title'],
                    options['source_key'], options['visibility'], options.get('owner_id'),
                    options['languages'], options['ocr_mode'], options['vision_mode'], options.get('vision_task'),
                    options['document_backend'], options['document_mode'])
            elif action == 'inspect':
                if not 1 <= options['limit'] <= 50 or (options.get('page') is not None and options['page'] < 1) or (
                        options.get('chunk') is not None and options['chunk'] < 0):
                    raise ValueError('Invalid page, chunk or limit')
                self.stdout.write(json.dumps(service.preview(options['job_id'], options['actor_id'],
                    options.get('page'), options.get('chunk'), options['limit']), ensure_ascii=False, indent=2))
                return
            else:
                job = service.action(options['job_id'], options['actor_id'], action, options.get('accept_warnings', False))
            self.stdout.write(json.dumps(service.preview(job.pk, options['actor_id']), ensure_ascii=False, indent=2))
        except ObjectDoesNotExist:
            raise CommandError('Import, page or document not found') from None
        except ValidationError:
            raise CommandError('Invalid import identifier') from None
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from None
