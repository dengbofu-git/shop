"""Global provider-trade uniqueness shared by combined and legacy payments."""
import re
from decimal import Decimal, InvalidOperation

from django.utils import timezone

from orders.reservations import ReservationError
from .models import PaymentReceipt


def validate_receipt(trade_no, amount):
    if not isinstance(trade_no, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', trade_no):
        raise ReservationError('INVALID_PAYMENT_TRADE', '支付流水无效', 400)
    try:
        value = Decimal(str(amount))
        if not value.is_finite() or value <= 0 or value != value.quantize(Decimal('.01')):
            raise ValueError()
    except (InvalidOperation, ValueError, TypeError):
        raise ReservationError('INVALID_PAYMENT_AMOUNT', '支付金额无效', 400)
    return value


def _record(trade_no, amount, *, payment=None, order=None):
    """Caller holds buyer, payment and order locks inside its atomic operation.

    get_or_create's unique-index retry serializes an identical trade arriving
    for DIFFERENT buyers, whose ordinary buyer locks cannot coordinate them.
    """
    amount = validate_receipt(trade_no, amount)
    receipt, _ = PaymentReceipt.objects.get_or_create(trade_no=trade_no, defaults={
        'payment_id': payment.pk if payment else None,
        'legacy_order_id': order.pk if order else None,
        'amount': amount, 'currency': 'CNY', 'received_at': timezone.now(),
    })
    receipt = PaymentReceipt.objects.select_for_update().get(pk=receipt.pk)
    if (receipt.payment_id != (payment.pk if payment else None) or
            receipt.legacy_order_id != (order.pk if order else None)):
        raise ReservationError('PAYMENT_TRADE_CONFLICT', '支付流水已归属另一笔付款', 400)
    if receipt.amount != amount:
        raise ReservationError('PAYMENT_AMOUNT_MISMATCH', '支付金额不匹配', 400)
    if receipt.outcome == 'legacy_reference':
        # This is the first actual verified notification, not a backfilled proof.
        receipt.currency = 'CNY'
        receipt.received_at = timezone.now()
        receipt.outcome = 'pending'
        receipt.save(update_fields=['currency', 'received_at', 'outcome'])
    return receipt


def record_combined_receipt(payment, trade_no, amount):
    return _record(trade_no, amount, payment=payment)


def record_legacy_receipt(order, trade_no, amount):
    return _record(trade_no, amount, order=order)


def finalize_legacy_receipt(receipt, order):
    if receipt.outcome in ('paid', 'review'):
        return receipt
    paid = not order.payment_exception and order.paid_at is not None and order.status in (2, 3, 4)
    receipt.outcome = 'paid' if paid else 'review'
    receipt.review_reason = '' if paid else (order.payment_exception or 'legacy_payment_review')
    receipt.save(update_fields=['outcome', 'review_reason'])
    return receipt
