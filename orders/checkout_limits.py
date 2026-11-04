"""One limit for the actual checkout selection, before any inventory work."""
import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def checkout_sku_limit():
    value = getattr(settings, 'RESERVATION_MAX_SKUS_PER_CHECKOUT', 20)
    if type(value) is not int or value < 1:
        raise ImproperlyConfigured('RESERVATION_MAX_SKUS_PER_CHECKOUT must be a positive integer')
    return value


def validate_checkout_size(items):
    from .reservations import ReservationError
    limit = checkout_sku_limit()
    if len(items) > limit:
        raise ReservationError('CHECKOUT_SKU_LIMIT',
            '单次最多结算%s种商品，请减少勾选数量后分批结算' % limit,
            400, checkout_sku_limit=limit)


def cart_selection(values, requested=None):
    """Read-only parsing; never clean or upgrade a rejected cart."""
    from .reservations import ReservationError, positive
    ids = None if requested is None else set(requested)
    items, snapshots = {}, {}
    for key, value in values.items():
        sid = positive(key.decode('utf-8') if isinstance(key, bytes) else key)
        row = json.loads(value)
        if not isinstance(row, dict) or not isinstance(row.get('status', True), bool):
            raise ReservationError('INVALID_CART', '采购车商品格式不正确', 400)
        count = positive(row.get('count'))
        if row.get('status') is True and (ids is None or sid in ids):
            if sid in items:
                raise ReservationError('INVALID_CART', '采购车商品重复，请重新加载', 400)
            items[sid], snapshots[sid] = count, row
    validate_checkout_size(items)
    if ids and set(items) != ids:
        raise ReservationError('CART_CHANGED', '采购车已变化，请返回重新选择', 409)
    return items, snapshots
