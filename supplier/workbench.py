from django.db.models import Q


def owned_items(user):
    # A recorded seller takes precedence over today's product owner. Legacy
    # unsnapshotted lines follow the existing merchant order-list visibility.
    return Q(merchant_snapshot=user) | Q(merchant_snapshot__isnull=True, sku__spu__merchant=user)
