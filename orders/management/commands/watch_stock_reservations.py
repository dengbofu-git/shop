import time
from django.core.management.base import BaseCommand
from django.db import close_old_connections
from orders.reservations import expire_orders
from orders.cart_cleanup import drain_cleanup


class Command(BaseCommand):
    help='独立到期清理进程；应与Web服务一同受进程管理器监控。'
    def handle(self,*args,**options):
        while True:
            close_old_connections()
            try:
                expire_orders()
                drain_cleanup()
            except Exception:
                import logging
                logging.getLogger(__name__).exception('reservation.expiry.failed')
            time.sleep(30)
