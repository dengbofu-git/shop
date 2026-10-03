# -*- coding: utf-8 -*-
"""
数据迁移：创建报关专员账号 dddddd（密码从环境配置读取）
"""
from django.conf import settings
from django.db import migrations


def md5_hash(s):
    import hashlib
    h = hashlib.md5()
    h.update(s.encode())
    return h.hexdigest()


def create_customs_user(apps, schema_editor):
    UserProfile = apps.get_model('users', 'UserProfile')

    user, created = UserProfile.objects.get_or_create(
        username='dddddd',
        defaults={
            'password': md5_hash(settings.CUSTOMS_INITIAL_PASSWORD),
            'email': 'dddddd@dadashop.com',
            'phone': '13800138001',
            'user_type': 'merchant',
            'is_active': True,
            'shop_name': '报关专员',
            'shop_description': '报关专员账号',
        }
    )
    if not created:
        UserProfile.objects.filter(username='dddddd').update(
            password=md5_hash(settings.CUSTOMS_INITIAL_PASSWORD),
            user_type='merchant',
            is_active=True,
            shop_name='报关专员',
        )


def reverse_create_customs(apps, schema_editor):
    UserProfile = apps.get_model('users', 'UserProfile')
    UserProfile.objects.filter(username='dddddd').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_create_admin_user'),
    ]

    operations = [
        migrations.RunPython(create_customs_user, reverse_create_customs),
    ]
