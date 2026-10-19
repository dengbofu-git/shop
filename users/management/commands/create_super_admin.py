# -*- coding: utf-8 -*-
"""
创建超级端账号（初始密码从 .env 读取）
用法: python manage.py create_super_admin
"""
from django.conf import settings
from django.core.management.base import BaseCommand
from users.models import UserProfile, Role, UserRole
from users import permissions as perm_constants
from tea_saas.utils import md5


class Command(BaseCommand):
    help = '创建超级端账号，并分配超级管理员角色'

    def handle(self, *args, **options):
        username = 'admin'
        password = settings.ADMIN_INITIAL_PASSWORD

        user, created = UserProfile.objects.get_or_create(
            username=username,
            defaults={
                'password': md5(password),
                'email': f'{username}@tea_saas.com',
                'phone': '13800000000',
                'user_type': 'customer',
                'is_active': True,
            }
        )

        if not created:
            UserProfile.objects.filter(username=username).update(
                password=md5(password),
                is_active=True,
            )
            user = UserProfile.objects.get(username=username)
            self.stdout.write(self.style.SUCCESS(f'已更新超级端账号: {username}'))
        else:
            self.stdout.write(self.style.SUCCESS(f'已创建超级端账号: {username}'))

        super_admin_role = Role.objects.filter(code=perm_constants.ROLE_SUPER_ADMIN).first()
        if super_admin_role:
            UserRole.objects.get_or_create(
                user_profile=user,
                role=super_admin_role
            )
            self.stdout.write(self.style.SUCCESS(f'已分配角色: {super_admin_role.name}'))
        else:
            self.stdout.write(self.style.WARNING('未找到超级管理员角色，请先执行: python manage.py seed_rbac'))

        self.stdout.write('')
        self.stdout.write('超级端账号: %s' % username)
        self.stdout.write('初始密码由配置提供，不在终端显示')
        self.stdout.write('终端登录: http://127.0.0.1:8000/terminal_login.html')
