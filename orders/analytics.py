"""Shared sales recognition rule for platform and merchant dashboards."""
from django.db.models import Q


def sales_eligible_orders():
    """Fully paid merchandise, excluding returned trials and cancelled presales."""
    return (
        Q(order_type='standard', status__in=(2, 3, 4))
        | Q(order_type='trial', trialorder__status__in=(2, 3, 4, 5, 6, 8))
        | (Q(order_type='presale', presaleorder__deposit_paid=True,
             presaleorder__balance_paid=True) & ~Q(presaleorder__status=7))
    )
