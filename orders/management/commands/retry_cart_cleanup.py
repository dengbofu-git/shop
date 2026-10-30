import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from orders.cart_cleanup import drain_cleanup


class Command(BaseCommand):
    help = '重试持久化采购车清理任务；--watch 持续运行，应由进程管理器监管。'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true')
        parser.add_argument('--interval', type=int, default=10)
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        if options['interval'] < 1 or not 1 <= options['limit'] <= 1000:
            from django.core.management.base import CommandError
            raise CommandError('interval须为正数，limit须为1～1000')
        while True:
            close_old_connections()
            try:
                count = drain_cleanup(limit=options['limit'])
                self.stdout.write(f'cart cleanup completed: {count}')
            except Exception:
                import logging
                logging.getLogger(__name__).exception('cart.cleanup.worker_failed')
                if not options['watch']: raise
            if not options['watch']: return
            time.sleep(options['interval'])
