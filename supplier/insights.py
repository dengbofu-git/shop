"""Merchant sales observations; never infer markets or customer preferences."""
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Count, DecimalField, ExpressionWrapper, F, Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from orders.analytics import sales_eligible_orders
from orders.models import OrderGoods, OrderInfo
from users.access import account_access
from users.decorators import get_user_from_request
from .workbench import owned_items


PRICE_BUCKETS = (
    ('under_80', Q(price__lt=80)),
    ('80_to_120', Q(price__gte=80, price__lt=120)),
    ('120_to_280', Q(price__gte=120, price__lt=280)),
    ('280_plus', Q(price__gte=280)),
)


def money(value):
    return format(Decimal(value or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP), '.2f')


def build_supplier_insights(user, now=None):
    now = now or timezone.localtime()
    start = now - timedelta(days=365)
    eligible = OrderInfo.objects.filter(sales_eligible_orders()).values('pk')
    lines = OrderGoods.objects.filter(owned_items(user), order_info_id__in=eligible,
        order_info__created_time__gte=start, order_info__created_time__lt=now)
    amount = ExpressionWrapper(F('count') * F('price'),
                               output_field=DecimalField(max_digits=24, decimal_places=2))
    total = lines.aggregate(amount=Sum(amount), quantity=Sum('count'), orders=Count('order_info_id', distinct=True))
    # Group by product ID as well as name: variants belong to one product,
    # while unrelated products with identical names must never be merged.
    products = lines.values('sku__spu_id', 'sku__spu__name').annotate(quantity=Sum('count'), amount=Sum(amount))

    def top(ordering):
        return [{'product_id': row['sku__spu_id'], 'name': row['sku__spu__name'],
                 'quantity': row['quantity'], 'amount': money(row['amount'])}
                for row in products.order_by(*ordering)[:5]]

    monthly = []
    for offset in range(5, -1, -1):
        index = now.year * 12 + now.month - 1 - offset
        begin = now.replace(year=index // 12, month=index % 12 + 1,
                            day=1, hour=0, minute=0, second=0, microsecond=0)
        end = begin.replace(year=(index + 1) // 12, month=(index + 1) % 12 + 1)
        aggregate = lines.filter(order_info__created_time__gte=begin,
            order_info__created_time__lt=end).aggregate(amount=Sum(amount), orders=Count('order_info_id', distinct=True))
        monthly.append({'month': begin.strftime('%Y-%m'), 'order_count': aggregate['orders'],
                        'amount': money(aggregate['amount'])})

    # A price range describes the historical paid unit price, not current
    # catalogue prices or packaging. Only positive purchased quantities qualify.
    priced = lines.filter(count__gt=0, price__gte=0)
    distribution = priced.aggregate(total=Sum('count'), **{
        code: Sum('count', filter=condition) for code, condition in PRICE_BUCKETS})
    units = distribution['total'] or 0
    buckets = []
    for code, _ in PRICE_BUCKETS:
        count = distribution[code] or 0
        percent = float((Decimal(count) * 100 / units).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)) if units else None
        buckets.append({'code': code, 'quantity': count, 'percent': percent})
    return {
        'scope': 'merchant_only', 'currency': 'CNY',
        'period': {'code': 'year', 'start': start.isoformat(), 'end': now.isoformat()},
        'totals': {'amount': money(total['amount']), 'quantity': total['quantity'] or 0, 'paid_orders': total['orders']},
        'top_products': top(('-quantity', '-amount', 'sku__spu_id')),
        'sales_top_products': top(('-amount', '-quantity', 'sku__spu_id')),
        'monthly': monthly,
        'price_distribution': {'quantity': units, 'buckets': buckets,
                               'excluded_lines': lines.exclude(count__gt=0, price__gte=0).count()},
        # TODO: structured buyer taste signals and a verified region/country
        # source do not exist. Never derive a country from an order-number hash.
        'taste_preferences': None, 'regional_sales': None,
        # TODO: integrate attributed, dated industry sources before displaying
        # export trends, competitors or policy/regulatory news. News posts from
        # merchants alone are not an authoritative industry dataset.
        'industry': {'export_trend': None, 'competitors': None, 'policies': None},
        'generated_at': now.isoformat(),
    }


@never_cache
def supplier_insights(request):
    if request.method != 'GET':
        response = JsonResponse({'code': 405, 'error': '仅支持读取'}, status=405)
        response['Allow'] = 'GET'
        return response
    user, error = get_user_from_request(request)
    if error is not None or not user.is_active:
        return JsonResponse({'code': 401, 'error': '请先登录有效账号'}, status=401)
    if account_access(user)['redirect_url'] != '/merchant_dashboard.html':
        return JsonResponse({'code': 403, 'error': '需要商家账号'}, status=403)
    return JsonResponse({'code': 200, 'data': build_supplier_insights(user)})
