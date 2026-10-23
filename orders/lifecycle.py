"""Order subtype state and merchant mutation boundaries, without rewriting history."""
from django.db.models import Q
from django.db.models.functions import Coalesce


class OrderActionError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def state_record(order):
    if order.order_type == 'standard':
        return order
    relation = {'trial': 'trialorder', 'presale': 'presaleorder'}.get(order.order_type)
    return getattr(order, relation, None) if relation else None


def can_ship(order):
    record = state_record(order)
    if record is None:
        return False
    if order.order_type in ('standard', 'trial'):
        return record.status == 2
    return record.status == 4 and record.deposit_paid and record.balance_paid


def can_delete(order):
    # The retained route cancels unpaid standard orders; never deletes history.
    return order.order_type == 'standard' and order.status == 1 and not order.paid_at


def merchant_ids(order):
    return set(order.ordergoods_set.annotate(owner=Coalesce('merchant_snapshot_id', 'sku__spu__merchant_id')).values_list('owner', flat=True))


def require_single_merchant(order, user):
    ids = merchant_ids(order)
    if user.pk not in ids:
        raise OrderActionError('无权操作此订单', 403)
    if ids != {user.pk}:
        raise OrderActionError('历史混合订单需由平台先处理商家拆分，不能整单操作', 409)


def status_filter(value):
    if value == 0:
        return Q(order_type='standard', status=0)
    if value == 1:
        return Q(order_type='standard', status=1) | Q(order_type='trial', trialorder__status=1) | Q(
            order_type='presale', presaleorder__status__in=(1, 2, 3))
    if value == 2:
        return Q(order_type='standard', status=2) | Q(order_type='trial', trialorder__status=2) | Q(
            order_type='presale', presaleorder__status=4, presaleorder__deposit_paid=True, presaleorder__balance_paid=True)
    if value == 3:
        return Q(order_type='standard', status=3) | Q(order_type='trial', trialorder__status=3) | Q(
            order_type='presale', presaleorder__status=5)
    if value == 4:
        return Q(order_type='standard', status=4) | Q(order_type='trial', trialorder__status=8) | Q(
            order_type='presale', presaleorder__status=6)
    return Q(pk__in=[])
