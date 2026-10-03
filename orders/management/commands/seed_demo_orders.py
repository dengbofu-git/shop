"""生成模拟订单数据（含订单行），供供应商数据中心与订单管理展示。"""
import random
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from goods.models import SKU
from orders.models import OrderGoods, OrderInfo
from users.models import Address, UserProfile

PREFIX = 'SIM'
REGIONS = (
    '广东省广州市天河区',
    '广东省深圳市南山区',
    '浙江省杭州市西湖区',
    '福建省福州市鼓楼区',
)


class Command(BaseCommand):
    help = '为指定供应商商品生成模拟订单（默认 100 条）'

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=100, help='生成订单数量')
        parser.add_argument('--merchant', type=str, default='', help='供应商登录名，默认取第一个 merchant')
        parser.add_argument('--clear', action='store_true', help='先删除 SIM 开头的模拟订单')

    @transaction.atomic
    def handle(self, *args, **options):
        count = max(1, options['count'])
        merchant_username = options['merchant'].strip()

        if options['clear']:
            removed = OrderInfo.objects.filter(order_id__startswith=PREFIX).count()
            OrderInfo.objects.filter(order_id__startswith=PREFIX).delete()
            self.stdout.write(self.style.WARNING(f'已删除 {removed} 条模拟订单'))

        if merchant_username:
            merchant = UserProfile.objects.filter(username=merchant_username).first()
        else:
            merchant = (
                UserProfile.objects.filter(user_type='merchant', spu__isnull=False)
                .distinct()
                .first()
            ) or UserProfile.objects.filter(user_type='merchant').first()
        if not merchant:
            self.stderr.write('未找到 merchant 用户，请用 --merchant 指定')
            return

        skus = list(SKU.objects.filter(spu__merchant=merchant)[:20])
        if not skus:
            self.stderr.write(f'供应商 {merchant.username} 下无 SKU，请先维护商品')
            return

        buyers = list(UserProfile.objects.filter(user_type='customer')[:10])
        if not buyers:
            buyers = [merchant]

        existing = OrderInfo.objects.filter(order_id__startswith=PREFIX).count()
        to_create = max(0, count - existing)
        if to_create == 0:
            self.stdout.write(self.style.SUCCESS(f'已有 {existing} 条 SIM 订单，无需新增'))
            return

        status_pool = [1] * 10 + [2] * 30 + [3] * 35 + [4] * 25
        now = timezone.now()
        created = 0

        for i in range(to_create):
            seq = existing + i + 1
            order_id = f'{PREFIX}{now.strftime("%Y%m%d")}{seq:04d}'
            buyer = random.choice(buyers)
            sku = random.choice(skus)
            qty = random.randint(1, 5)
            price = Decimal(str(sku.price))
            total = price * qty
            status = random.choice(status_pool)

            addr = Address.objects.filter(user_profile=buyer, is_delete=False).first()
            if addr:
                receiver, address, mobile, tag = (
                    addr.receiver, addr.address, addr.receiver_mobile, addr.tag,
                )
            else:
                receiver = buyer.username[:10] or '买家'
                address = random.choice(REGIONS) + '模拟路' + str(random.randint(1, 99)) + '号'
                mobile = buyer.phone or '13800138000'
                tag = '公司'

            days_ago = random.randint(0, 180)
            created_time = now - timezone.timedelta(days=days_ago, hours=random.randint(0, 23))

            order = OrderInfo.objects.create(
                user_profile=buyer,
                order_id=order_id,
                order_type='standard',
                total_amount=total,
                total_count=qty,
                pay_method=1,
                freight=Decimal('0'),
                status=status,
                receiver=receiver,
                address=address,
                receiver_mobile=mobile,
                tag=tag,
            )
            OrderInfo.objects.filter(pk=order.pk).update(
                created_time=created_time,
                updated_time=created_time + timezone.timedelta(days=random.randint(1, 5)),
            )
            OrderGoods.objects.create(
                order_info=order,
                sku=sku,
                count=qty,
                price=price,
            )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'已为供应商 {merchant.username} 生成 {created} 条模拟订单（SKU 数 {len(skus)}）'
        ))
