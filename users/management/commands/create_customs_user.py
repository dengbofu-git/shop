# -*- coding: utf-8 -*-
"""
创建报关专员账号（初始密码从 .env 读取）
用法: python manage.py create_customs_user
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from users.models import UserProfile
from dadashop.utils import md5


class Command(BaseCommand):
    help = '创建报关专员账号'

    def handle(self, *args, **options):
        username = 'dddddd'
        password = settings.CUSTOMS_INITIAL_PASSWORD

        user, created = UserProfile.objects.get_or_create(
            username=username,
            defaults={
                'password': md5(password),
                'email': f'{username}@dadashop.com',
                'phone': '13800138001',
                'user_type': 'merchant',
                'is_active': True,
                'shop_name': '报关专员',
                'shop_description': '报关专员账号',
            }
        )

        if not created:
            UserProfile.objects.filter(username=username).update(
                password=md5(password),
                user_type='merchant',
                is_active=True,
                shop_name='报关专员',
            )
            self.stdout.write(self.style.SUCCESS(f'已更新报关专员账号: {username}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'已创建报关专员账号: {username}'))

        self.stdout.write('')
        self.stdout.write('报关专员账号: %s' % username)
        self.stdout.write('初始密码由配置提供，不在终端显示')
        self.stdout.write('登录地址: http://127.0.0.1:8000/login.html （选择「报关专员」角色）')
        self.stdout.write('9710报关页: http://127.0.0.1:8000/customs_9710.html')
