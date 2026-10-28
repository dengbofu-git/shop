from django.core.management.base import BaseCommand
from orders.reservations import expire_orders


class Command(BaseCommand):
    help='释放到期未付款预留；重复执行安全，不处理已付预留。建议每分钟调度。'

    def handle(self,*args,**options):
        total=0
        while True:
            count=expire_orders()
            total+=count
            if count<500:break
        self.stdout.write('Expired reservations: %s'%total)
