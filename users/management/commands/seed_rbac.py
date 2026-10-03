from django.core.management.base import BaseCommand

from users import permissions as permission_codes
from users.models import Permission, Role, RolePermission


ROLES = (
    ('super_admin', '超级管理员', '拥有所有权限'),
    ('admin', '运营管理员', '运营管理权限'),
    ('customer_service', '客服', '客服权限'),
    ('finance', '财务', '财务管理权限'),
    ('supplier', '供应商', '供应商权限'),
    ('buyer', '买家', '买家权限'),
)

PERMISSIONS = (
    ('goods_manage', '商品管理', '商品管理权限'),
    ('order_manage', '订单管理', '订单管理权限'),
    ('user_manage', '用户管理', '用户管理权限'),
    ('data_view', '数据查看', '数据查看权限'),
    ('supplier_manage', '供应商管理', '供应商管理权限'),
    ('inventory_manage', '库存管理', '库存管理权限'),
    ('logistics_manage', '物流管理', '物流管理权限'),
    ('finance_manage', '财务管理', '财务管理权限'),
    ('system_config', '系统配置', '系统配置权限'),
)


class Command(BaseCommand):
    help = 'Create or update the RBAC roles, permissions, and their mappings.'

    def handle(self, *args, **options):
        roles = {
            code: Role.objects.update_or_create(
                code=code,
                defaults={'name': name, 'description': description},
            )[0]
            for code, name, description in ROLES
        }
        permissions = {
            code: Permission.objects.update_or_create(
                code=code,
                defaults={'name': name, 'description': description},
            )[0]
            for code, name, description in PERMISSIONS
        }

        assignments = 0
        for role_code, codes in permission_codes.ROLE_PERMISSIONS.items():
            role = roles.get(role_code)
            if role is None:
                self.stderr.write(f'Unknown role code: {role_code}')
                continue
            for code in codes:
                permission = permissions.get(code)
                if permission is None:
                    self.stderr.write(f'Unknown permission code: {code}')
                    continue
                _, created = RolePermission.objects.get_or_create(
                    role=role, permission=permission
                )
                assignments += created

        self.stdout.write(
            self.style.SUCCESS(
                f'RBAC seeded: {len(roles)} roles, {len(permissions)} permissions, '
                f'{assignments} new role-permission mappings.'
            )
        )
