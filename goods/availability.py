"""推荐及采购车共用当前可售范围，与下单的商家边界一致。"""
from inventory.availability import with_availability
from .models import SKU


def public_skus():
    """Launched products of active merchants, including temporarily empty stock."""
    return with_availability(SKU.objects.filter(
        is_launched=True, price__gt=0, spu__merchant__is_active=True))


def sellable_skus():
    return public_skus().filter(sellable_stock__gt=0)
