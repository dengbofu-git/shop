"""供应商数据中心：基于真实订单库的聚合统计"""
from collections import defaultdict
from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Sum, F, Q
from django.utils import timezone

from goods.models import SKU
from orders.models import OrderInfo, OrderGoods
from orders.analytics import sales_eligible_orders
from orders.lifecycle import status_filter
from supplier.models import SupplierSettlement


def _supplier_order_goods(user):
    from .workbench import owned_items
    return OrderGoods.objects.filter(owned_items(user)).select_related(
        'order_info', 'sku', 'sku__spu', 'sku__spu__catalog'
    )


def _supplier_orders(user):
    return OrderInfo.objects.filter(pk__in=_supplier_order_goods(user).values('order_info_id'))


def build_supplier_analytics(user, period='year'):
    now = timezone.localtime()
    if period == 'month':
        start = now - timedelta(days=30)
    elif period == 'quarter':
        start = now - timedelta(days=92)
    else:
        start = now - timedelta(days=365)

    ogs = _supplier_order_goods(user).filter(order_info__created_time__gte=start)
    orders = _supplier_orders(user).filter(created_time__gte=start)
    eligible_ids = OrderInfo.objects.filter(sales_eligible_orders()).values('pk')
    sales_ogs = ogs.filter(order_info_id__in=eligible_ids)

    line_total = Decimal('0')
    for og in sales_ogs:
        line_total += Decimal(str(og.count)) * Decimal(str(og.price))

    order_count = orders.count()
    paid_order_count = sales_ogs.values('order_info_id').distinct().count()
    pending_ship = orders.filter(status_filter(2)).count()
    in_transit = orders.filter(status_filter(3)).count()
    completed = orders.filter(status_filter(4)).count()
    unpaid = orders.filter(status_filter(1)).count()

    # 月度趋势（最近 6 个自然月）
    monthly = []
    for i in range(5, -1, -1):
        month_index = now.year * 12 + now.month - 1 - i
        month_start = now.replace(year=month_index // 12, month=month_index % 12 + 1,
                                  day=1, hour=0, minute=0, second=0, microsecond=0)
        month_end = month_start.replace(year=(month_index + 1) // 12,
                                        month=(month_index + 1) % 12 + 1)
        month_ogs = sales_ogs.filter(
            order_info__created_time__gte=month_start,
            order_info__created_time__lt=month_end,
        )
        m_sales = Decimal('0')
        m_count = month_ogs.values('order_info_id').distinct().count()
        for og in month_ogs:
            m_sales += Decimal(str(og.count)) * Decimal(str(og.price))
        monthly.append({
            'month': month_start.strftime('%Y-%m'),
            'label': month_start.strftime('%m月'),
            'order_count': m_count,
            'sales': float(m_sales),
        })

    cat_sales = defaultdict(lambda: Decimal('0'))
    for og in sales_ogs:
        cat = (og.sku.spu.catalog.name if og.sku.spu.catalog_id else '其他')
        cat_sales[cat] += Decimal(str(og.count)) * Decimal(str(og.price))

    total_f = float(line_total) or 1.0
    categories = []
    for name, amt in sorted(cat_sales.items(), key=lambda x: -x[1]):
        val = float(amt)
        categories.append({
            'name': name,
            'sales': val,
            'pct': round(val / total_f * 100, 1),
        })

    completion_rate = round(completed / order_count * 100, 1) if order_count else 0

    top_products = (
        sales_ogs.values(name=F('sku__name'))
        .annotate(qty=Sum('count'), amount=Sum(F('count') * F('price')))
        .order_by('-amount')[:5]
    )
    top_list = [
        {
            'name': row['name'] or '商品',
            'qty': row['qty'] or 0,
            'amount': float(row['amount'] or 0),
        }
        for row in top_products
    ]

    recent = []
    for order in orders.order_by('-created_time')[:8]:
        merchant_lines = ogs.filter(order_info=order)
        og = merchant_lines.first()
        pname = og.sku.name if og else '-'
        merchant_amount = sum((line.count * line.price for line in merchant_lines), Decimal('0'))
        recent.append({
            'order_id': order.order_id,
            'product': pname,
            'count': sum(line.count for line in merchant_lines),
            'amount': float(merchant_amount),
            'time': order.created_time.strftime('%m-%d %H:%M'),
            'status': order.status,
            'status_text': order.get_status_display_text(),
        })

    settlements_pending = SupplierSettlement.objects.filter(
        supplier=user, status='pending'
    ).count()

    return {
        'summary': {
            'total_sales': float(line_total),
            'total_sales_wan': round(float(line_total) / 10000, 2),
            'total_sales_display': '¥{:,.2f}'.format(line_total),
            'order_count': order_count,
            'paid_order_count': paid_order_count,
            'pending_ship': pending_ship,
            'in_transit': in_transit,
            'completed': completed,
            'unpaid': unpaid,
            'avg_order_amount': float((line_total / paid_order_count).quantize(Decimal('0.01'))) if paid_order_count else 0,
            # TODO: requires inventory valuation and a confirmed turnover basis.
            'inventory_turnover_days': None,
            'completion_rate': completion_rate,
        },
        'period': {'code': period, 'start': start.isoformat(), 'end': now.isoformat()},
        'sales_basis': '已全额付款的本店商品明细金额，不含运费；剔除已退货试单与已取消预售，按下单日期归集。',
        'monthly': monthly,
        # TODO: trusted destination and acquisition/conversion event sources.
        'regions': None,
        'categories': categories,
        'funnel': None,
        'top_products': top_list,
        'recent_orders': recent,
        'todos': {
            'unshipped': pending_ship,
            'settlement': settlements_pending,
            'unpaid': unpaid,
            'total': pending_ship + unpaid + settlements_pending,
        },
        'aux': {
            # TODO: independent partner, marketing, warehouse and survey sources.
            'monthly_new_partners': None,
            'campaign_roi': None,
            'warehouse_health_pct': None,
            'satisfaction_score': None,
        },
    }
