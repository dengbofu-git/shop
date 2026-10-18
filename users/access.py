"""Business portal routing and platform access, based on current database grants."""
from users.models import Role, Permission


PLATFORM_ROLES = frozenset(('super_admin', 'admin', 'customer_service', 'finance'))


def account_access(user):
    if not user.is_active:
        return {'roles': [], 'permissions': [], 'redirect_url': None}
    roles = list(Role.objects.filter(
        userrole__user_profile=user, is_active=True,
    ).values_list('code', flat=True))
    permissions = list(Permission.objects.filter(
        rolepermission__role__userrole__user_profile=user,
        rolepermission__role__is_active=True, is_active=True,
    ).values_list('code', flat=True).distinct())
    destination = None
    if PLATFORM_ROLES.intersection(roles):
        if 'data_view' in permissions:
            destination = '/admin_panel.html'
        elif 'user_manage' in permissions:
            destination = '/admin_users.html'
        elif 'system_config' in permissions:
            destination = '/admin_agents.html'
    elif user.is_merchant() or 'supplier' in roles:
        destination = '/merchant_dashboard.html'
    elif user.is_customer():
        destination = '/buyer_dashboard.html'
    return {'roles': sorted(roles), 'permissions': sorted(permissions),
            'redirect_url': destination}


def can_access_platform(access, permission_code):
    return bool(PLATFORM_ROLES.intersection(access['roles'])
                and permission_code in access['permissions'])
