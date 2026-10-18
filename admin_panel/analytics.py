"""Platform order statistics. No payment ledger or refund ledger is inferred."""
from datetime import timedelta
from decimal import Decimal

from django.db.models import Case, Count, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import TruncDate
from django.utils import timezone

from orders.models import OrderInfo
from orders.analytics import sales_eligible_orders
from users.access import PLATFORM_ROLES
from users.models import UserProfile, UserRole


def build_platform_overview():
    today = timezone.localdate()
    start = today - timedelta(days=29)
    money = DecimalField(max_digits=20, decimal_places=2)
    zero = Value(Decimal('0.00'), output_field=money)
    standard_paid = Q(order_type='standard', status__in=(2, 3, 4))
    trial_paid = Q(order_type='trial', trialorder__status__in=(2, 3, 4, 5, 6, 7, 8))
    sales_paid = sales_eligible_orders()
    orders = OrderInfo.objects.annotate(
        sales_value=Case(When(sales_paid, then=F('total_amount')), default=zero, output_field=money),
        flow_value=Case(
            When(standard_paid | trial_paid, then=F('total_amount') + F('freight')),
            When(order_type='presale', then=(
                Case(When(presaleorder__deposit_paid=True, then=F('presaleorder__deposit_amount')),
                     default=zero, output_field=money)
                + Case(When(presaleorder__balance_paid=True, then=F('presaleorder__balance_amount')),
                       default=zero, output_field=money))),
            default=zero, output_field=money),
    )
    summary = orders.aggregate(
        total_sales=Sum('sales_value'), total_flow=Sum('flow_value'),
        order_count=Count('pk'), paid_order_count=Count('pk', filter=sales_paid),
    )
    for key in ('total_sales', 'total_flow'):
        summary[key] = format(summary[key] or Decimal('0'), '.2f')
    # Platform operators are not counted as buyer accounts.
    platform_users = UserRole.objects.filter(
        role__code__in=PLATFORM_ROLES, role__is_active=True).values('user_profile_id')
    business_users = UserProfile.objects.exclude(pk__in=platform_users)
    summary['buyer_count'] = business_users.filter(user_type='customer').count()
    summary['merchant_count'] = business_users.filter(user_type='merchant').count()

    buckets = orders.filter(created_time__date__gte=start, created_time__date__lte=today).annotate(
        day=TruncDate('created_time')).values('day').annotate(
            sales=Sum('sales_value'), flow=Sum('flow_value'), order_count=Count('pk')).order_by('day')
    by_day = {row['day']: row for row in buckets}
    daily = []
    for offset in range(30):
        day = start + timedelta(days=offset)
        row = by_day.get(day, {})
        daily.append({'date': day.isoformat(), 'order_count': row.get('order_count', 0),
                      'sales': format(row.get('sales') or Decimal('0'), '.2f'),
                      'flow': format(row.get('flow') or Decimal('0'), '.2f')})

    state_filters = (
        ('待付款 / 待付尾款', Q(order_type='standard', status=1) | Q(order_type='trial', trialorder__status=1)
         | Q(order_type='presale', presaleorder__status__in=(1, 2, 3))),
        ('待发货', Q(order_type='standard', status=2) | Q(order_type='trial', trialorder__status=2)
         | Q(order_type='presale', presaleorder__status=4)),
        ('待收货', Q(order_type='standard', status=3) | Q(order_type='trial', trialorder__status=3)
         | Q(order_type='presale', presaleorder__status=5)),
        ('已完成', Q(order_type='standard', status=4) | Q(order_type='trial', trialorder__status=8)
         | Q(order_type='presale', presaleorder__status=6)),
        ('试用中 / 试用完成', Q(order_type='trial', trialorder__status__in=(4, 5))),
        ('退货中 / 已退货', Q(order_type='trial', trialorder__status__in=(6, 7))),
        ('已取消', Q(order_type='presale', presaleorder__status=7)),
    )
    counts = orders.aggregate(**{
        'state_{}'.format(i): Count('pk', filter=condition)
        for i, (_, condition) in enumerate(state_filters)
    })
    states = [{'name': name, 'count': counts['state_{}'.format(i)]}
              for i, (name, _) in enumerate(state_filters)]
    states.append({'name': '其他 / 状态缺失', 'count': summary['order_count'] - sum(row['count'] for row in states)})
    return {'summary': summary, 'daily': daily, 'states': states,
            'updated_at': timezone.localtime().isoformat(), 'currency': 'CNY'}
