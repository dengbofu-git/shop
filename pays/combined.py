"""Fixed checkout payment attempts; receipt and child transitions are atomic."""
from collections import defaultdict
from decimal import Decimal
import re

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from goods.models import SKU
from inventory.models import Inventory
from orders.models import CheckoutRequest, OrderGoods, OrderInfo, StockHold
from orders.reservations import ReservationError, _release_locked
from users.access import account_access
from users.models import UserProfile
from .models import PaymentAllocation, PaymentOrder
from .receipts import record_combined_receipt, validate_receipt


def lock_order_payments(order_id):
    """Called after the buyer lock and BEFORE locking an individual order."""
    ids = PaymentAllocation.objects.filter(order_id=order_id).values('payment_id')
    return list(PaymentOrder.objects.select_for_update().filter(pk__in=ids).order_by('pk'))


def invalidate_order_payments(order, reason):
    ids = PaymentAllocation.objects.filter(order=order).values('payment_id')
    PaymentOrder.objects.filter(pk__in=ids, status='pending').update(
        status='invalid', payment_exception=str(reason)[:80])


def _snapshot(order, now, holds=None, ledgers=None):
    if order.currency != 'CNY':
        raise ReservationError('CURRENCY_REVIEW_REQUIRED', '原记录币种未核验，请联系平台处理付款')
    if not order.reservation_managed or order.order_type != 'standard':
        raise ReservationError('LEGACY_ORDER_REQUIRES_REVIEW', '订单库存或类型需人工核验')
    if (order.status != 1 or order.paid_at or order.payment_trade_no or order.payment_exception or
            not order.expires_at or order.expires_at <= now):
        raise ReservationError('ORDER_NOT_PAYABLE', '订单已关闭或不再需要付款')
    items = list(order.ordergoods_set.order_by('pk'))
    merchants = {item.merchant_snapshot_id for item in items}
    if (not items or None in merchants or len(merchants) != 1 or
            any(item.currency != 'CNY' or item.price <= 0 or item.count <= 0 or
                (item.purchase_snapshot or {}).get('merchant_id') != item.merchant_snapshot_id
                for item in items)):
        raise ReservationError('ORDER_SNAPSHOT_REQUIRES_REVIEW', '订单金额或商家归属需人工核验')
    goods = sum((item.price * item.count for item in items), Decimal('0'))
    if (order.freight < 0 or goods + order.freight != order.total_amount or
            sum(item.count for item in items) != order.total_count):
        raise ReservationError('ORDER_AMOUNT_REQUIRES_REVIEW', '订单金额明细不一致，需人工核验')
    holds = list(StockHold.objects.filter(item__order_info=order).select_related('inventory')) if holds is None else holds
    quantities = defaultdict(int)
    item_map = {item.pk: item for item in items}
    for hold in holds:
        inventory = hold.inventory if ledgers is None else ledgers.get(hold.inventory_id)
        if (hold.state != 'reserved' or hold.item_id not in item_map or inventory is None or
                inventory.sku_id != item_map[hold.item_id].sku_id or
                inventory.reserved_quantity < hold.quantity):
            raise ReservationError('INVENTORY_INCONSISTENT', '订单预留不完整，需人工核验')
        quantities[hold.item_id] += hold.quantity
    if any(quantities[item.pk] != item.count for item in items):
        raise ReservationError('INVENTORY_INCONSISTENT', '订单预留不完整，需人工核验')
    return {'merchant_id': next(iter(merchants)),
        'merchant_name': (items[0].purchase_snapshot or {}).get('merchant_name') or '',
        'goods_amount': goods, 'freight_amount': order.freight, 'amount': order.total_amount}


def _same_allocations(payment, allocations, snapshots):
    if {a.order_id for a in allocations} != set(snapshots):
        return False
    fields = ('merchant_id', 'merchant_name', 'goods_amount', 'freight_amount', 'amount')
    return (sum((a.amount for a in allocations), Decimal('0')) == payment.total_amount and
            all(all(getattr(a, key) == snapshots[a.order_id][key] for key in fields) for a in allocations))


def prepare_checkout_payment(user, checkout_id):
    # Refusals which invalidate an issued attempt must survive the HTTP error.
    result = _prepare_checkout_payment(user, checkout_id)
    if isinstance(result, ReservationError):
        raise result
    return result


def _prepare_checkout_payment(user, checkout_id):
    if (isinstance(checkout_id, bool) or not re.fullmatch(r'[1-9][0-9]{0,18}', str(checkout_id)) or
            int(checkout_id) > 9223372036854775807):
        raise ReservationError('INVALID_CHECKOUT', '结算编号无效', 400)
    with transaction.atomic():
        buyer = UserProfile.objects.select_for_update().get(pk=user.pk)
        if not buyer.is_active:
            raise ReservationError('UNAUTHENTICATED', '请先登录有效账号', 401)
        if account_access(buyer)['redirect_url'] != '/buyer_dashboard.html':
            raise ReservationError('FORBIDDEN', '仅本人买家可以付款', 403)
        checkout = CheckoutRequest.objects.filter(pk=checkout_id, user=buyer).first()
        if checkout is None:
            raise ReservationError('CHECKOUT_NOT_FOUND', '结算记录不存在', 404)
        attempts = list(PaymentOrder.objects.select_for_update().filter(checkout=checkout).order_by('pk'))
        payment = next((p for p in attempts if p.status == 'pending'), None)
        if attempts and payment is None:
            raise ReservationError('PAYMENT_ATTEMPT_INVALID', '原付款已结束或需核验，请查看订单或联系平台')
        allocations = list(payment.allocations.order_by('order_id')) if payment else []
        orders = list(OrderInfo.objects.select_for_update().filter(
            Q(checkout_request=checkout) | Q(pk__in=[a.order_id for a in allocations])).order_by('pk'))
        now = timezone.now()
        snapshots = {}
        try:
            for order in orders:
                if order.checkout_request_id != checkout.pk or order.user_profile_id != buyer.pk:
                    raise ReservationError('ORDER_SNAPSHOT_REQUIRES_REVIEW', '订单结算归属已变化')
                if order.status == 0 or order.paid_at or order.status in (2, 3, 4):
                    continue
                snapshots[order.pk] = _snapshot(order, now)
            if not snapshots:
                raise ReservationError('ORDER_NOT_PAYABLE', '没有需要付款的有效订单')
            deadline = min(o.expires_at for o in orders if o.pk in snapshots)
            if payment:
                if (payment.expires_at <= now or payment.expires_at != deadline or
                        not _same_allocations(payment, allocations, snapshots)):
                    raise ReservationError('PAYMENT_ATTEMPT_INVALID', '付款明细已变化，请联系平台核验原付款')
                return payment
        except ReservationError as exc:
            if payment:
                payment.status = 'invalid'
                payment.payment_exception = 'checkout_changed'
                payment.save(update_fields=['status', 'payment_exception'])
                return ReservationError('PAYMENT_ATTEMPT_INVALID', '原付款已失效，请查看订单或联系平台核验')
            raise exc
        payment = PaymentOrder.objects.create(buyer=buyer, checkout=checkout,
            total_amount=sum((s['amount'] for s in snapshots.values()), Decimal('0')),
            currency='CNY', expires_at=deadline)
        PaymentAllocation.objects.bulk_create([
            PaymentAllocation(payment=payment, order_id=pk, **snapshot)
            for pk, snapshot in snapshots.items()])
        return payment


def _lock_group_stock(orders):
    ids = sorted(set(OrderGoods.objects.filter(order_info__in=orders).values_list('sku_id', flat=True)))
    list(SKU.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    ledgers = {row.pk: row for row in Inventory.objects.select_for_update().filter(sku_id__in=ids).order_by('pk')}
    holds = defaultdict(list)
    for hold in StockHold.objects.select_for_update().filter(item__order_info__in=orders).order_by('pk'):
        holds[hold.item_id].append(hold)
    item_orders = dict(OrderGoods.objects.filter(order_info__in=orders).values_list('pk', 'order_info_id'))
    grouped = defaultdict(list)
    for item_id, rows in holds.items():
        grouped[item_orders[item_id]].extend(rows)
    return ledgers, grouped


def _review(payment, allocations, orders, receipt, now, reason):
    # The entire group stock is already locked in sorted order before per-order
    # release helpers reacquire their own subsets. Never touch a lawful payment.
    for order in orders:
        if order.status == 1 and not order.paid_at:
            _release_locked(order, 'payment_review', now)
            order.payment_exception = 'combined_payment_review'
            order.save(update_fields=['payment_exception', 'updated_time'])
    payment.status = 'review'
    payment.payment_exception = reason
    payment.save(update_fields=['status', 'payment_exception'])
    PaymentAllocation.objects.filter(pk__in=[a.pk for a in allocations]).update(status='review')
    receipt.outcome = 'review'
    receipt.review_reason = reason
    receipt.save(update_fields=['outcome', 'review_reason'])
    return payment


def confirm_combined_payment(payment_id, trade_no, amount):
    amount = validate_receipt(trade_no, amount)
    owner = PaymentOrder.objects.filter(pk=payment_id).values_list('buyer_id', flat=True).first()
    if owner is None:
        raise ReservationError('PAYMENT_NOT_FOUND', '付款记录不存在', 404)
    with transaction.atomic():
        UserProfile.objects.select_for_update().get(pk=owner)
        payment = PaymentOrder.objects.select_for_update().get(pk=payment_id)
        allocations = list(payment.allocations.order_by('order_id'))
        orders = list(OrderInfo.objects.select_for_update().filter(
            pk__in=[a.order_id for a in allocations]).order_by('pk'))
        if amount != payment.total_amount:
            raise ReservationError('PAYMENT_AMOUNT_MISMATCH', '支付金额不匹配', 400)
        receipt = record_combined_receipt(payment, trade_no, amount)
        if receipt.outcome in ('paid', 'review'):
            return payment
        if payment.status == 'paid':
            receipt.outcome = 'review'
            receipt.review_reason = 'duplicate_payment_review_required'
            receipt.save(update_fields=['outcome', 'review_reason'])
            payment.payment_exception = receipt.review_reason
            payment.save(update_fields=['payment_exception'])
            return payment
        now = timezone.now()
        ledgers, holds = _lock_group_stock(orders)
        changed = (payment.status != 'pending' or payment.expires_at <= now or not allocations or
            len(orders) != len(allocations) or
            any(o.status != 1 or o.paid_at or o.expires_at is None or o.expires_at <= now or
                o.checkout_request_id != payment.checkout_id or o.user_profile_id != payment.buyer_id
                for o in orders))
        if changed:
            return _review(payment, allocations, orders, receipt, now, 'combined_payment_review_required')
        snapshots = {}
        for order in orders:
            # Incomplete holds are an integrity failure: roll back the WHOLE
            # notification, including its receipt, rather than partially pay.
            try:
                snapshots[order.pk] = _snapshot(order, now, holds[order.pk], ledgers)
            except ReservationError as exc:
                if exc.code == 'INVENTORY_INCONSISTENT':
                    raise
                return _review(payment, allocations, orders, receipt, now, 'checkout_changed_review_required')
        ledger_totals = defaultdict(int)
        for rows in holds.values():
            for hold in rows:
                ledger_totals[hold.inventory_id] += hold.quantity
        if any(ledgers[pk].reserved_quantity < quantity for pk, quantity in ledger_totals.items()):
            raise ReservationError('INVENTORY_INCONSISTENT', '库存预留记录不一致，请联系管理员')
        if not _same_allocations(payment, allocations, snapshots):
            return _review(payment, allocations, orders, receipt, now, 'checkout_changed_review_required')
        for order in orders:
            StockHold.objects.filter(pk__in=[h.pk for h in holds[order.pk]]).update(state='paid')
            order.status = 2
            order.paid_at = now
            order.save(update_fields=['status', 'paid_at', 'updated_time'])
        PaymentAllocation.objects.filter(payment=payment).update(status='paid')
        payment.status = 'paid'
        payment.paid_at = now
        payment.save(update_fields=['status', 'paid_at'])
        receipt.outcome = 'paid'
        receipt.save(update_fields=['outcome'])
        return payment
