"""Shared sales recognition rule for platform and merchant dashboards."""
from django.db.models import Q


def sales_status_eligible_orders():
    """Original sales status qualification, independent of recorded currency."""
    return (
        Q(order_type='standard', status__in=(2, 3, 4))
        | Q(order_type='trial', trialorder__status__in=(2, 3, 4, 5, 6, 8))
        | (Q(order_type='presale', presaleorder__deposit_paid=True,
             presaleorder__balance_paid=True) & ~Q(presaleorder__status=7))
    )


def sales_eligible_orders():
    """Fully paid CNY merchandise, excluding returned trials/cancelled presales."""
    return sales_status_eligible_orders() & Q(currency='CNY')
