"""Admission units for independently payable merchant orders.

The caller holds the buyer row lock until all new child orders commit. A group
only occupies a slot while it has an unexpired, unpaid physical stock hold.
Historical managed orders without a checkout link remain separate groups.
"""
from django.conf import settings

from .models import OrderInfo


def max_unpaid_checkouts():
    return settings.RESERVATION_MAX_UNPAID_CHECKOUTS


def pending_checkout_groups(user, now):
    rows = OrderInfo.objects.filter(
        user_profile=user, reservation_managed=True, status=1,
        paid_at__isnull=True, expires_at__gt=now,
        ordergoods__stock_holds__state='reserved',
    ).values_list('pk', 'checkout_request_id').distinct()
    return len({('checkout', checkout) if checkout is not None else ('order', pk)
                for pk, checkout in rows})
