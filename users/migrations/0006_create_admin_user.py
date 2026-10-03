# -*- coding: utf-8 -*-
"""
数据迁移：创建管理端账号 admin（密码从环境配置读取）
"""
from django.conf import settings
from django.db import migrations


def md5_hash(s):
    import hashlib
    h = hashlib.md5()
    h.update(s.encode())
    return h.hexdigest()


def create_admin_user(apps, schema_editor):
    UserProfile = apps.get_model('users', 'UserProfile')
    Role = apps.get_model('users', 'Role')
    UserRole = apps.get_model('users', 'UserRole')

    user, created = UserProfile.objects.get_or_create(
        username='admin',
        defaults={
            'password': md5_hash(settings.ADMIN_INITIAL_PASSWORD),
            'email': 'admin@dadashop.com',
            'phone': '13800000000',
            'user_type': 'customer',
            'is_active': True,
        }
    )
    if not created:
        UserProfile.objects.filter(username='admin').update(
            password=md5_hash(settings.ADMIN_INITIAL_PASSWORD),
            is_active=True,
        )

    super_admin_role = Role.objects.filter(code='super_admin').first()
    if super_admin_role:
        UserRole.objects.get_or_create(
            user_profile=user,
            role=super_admin_role
        )


def reverse_create_admin(apps, schema_editor):
    UserProfile = apps.get_model('users', 'UserProfile')
    UserProfile.objects.filter(username='admin').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0005_permission_role_rolepermission_userrole'),
    ]

    operations = [
        migrations.RunPython(create_admin_user, reverse_create_admin),
    ]
