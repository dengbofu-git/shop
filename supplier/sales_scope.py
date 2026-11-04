"""Currency completeness for an already merchant- and period-scoped order set."""
from django.db.models import Count, Q

from orders.analytics import sales_status_eligible_orders


def build_sales_scope(orders):
    """Count qualified orders once, without inferring or rewriting currency.

    Callers provide their existing ownership and date restrictions before any
    currency filter, so this metadata describes the same reporting window.
    """
    counts = orders.filter(sales_status_eligible_orders()).aggregate(
        status_order_count=Count('pk', distinct=True),
        cny_order_count=Count('pk', distinct=True, filter=Q(currency='CNY')),
        unknown_currency_order_count=Count(
            'pk', distinct=True, filter=Q(currency__isnull=True) | Q(currency='')),
        other_currency_order_count=Count(
            'pk', distinct=True,
            filter=Q(currency__isnull=False) & ~Q(currency='') & ~Q(currency='CNY')),
    )
    excluded = counts['unknown_currency_order_count'] + counts['other_currency_order_count']
    state = 'complete'
    if excluded:
        state = 'partial' if counts['cny_order_count'] else 'unavailable'
    return {'currency': 'CNY', **counts, 'financial_state': state}
