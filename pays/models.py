"""Payment attempts, immutable allocations and shared provider receipt facts."""
import uuid

from django.core.exceptions import ValidationError
from django.db import models


def payment_id():
    return 'pay_' + uuid.uuid4().hex


class ImmutableSnapshot(models.Model):
    immutable_fields = ()

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if not self._state.adding:
            old = type(self).objects.get(pk=self.pk)
            if any(getattr(old, name) != getattr(self, name) for name in self.immutable_fields):
                raise ValidationError('付款金额和归属快照不可修改')
        return super().save(*args, **kwargs)


class PaymentOrder(ImmutableSnapshot):
    payment_id = models.CharField(max_length=36, primary_key=True, default=payment_id, editable=False)
    buyer = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT, related_name='checkout_payments')
    checkout = models.ForeignKey('orders.CheckoutRequest', on_delete=models.PROTECT, related_name='payments')
    currency = models.CharField(max_length=3, default='CNY')
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=12, default='pending', choices=[
        ('pending', '待付款'), ('paid', '已付款'), ('invalid', '已失效'), ('review', '待核验')])
    payment_exception = models.CharField(max_length=80, blank=True, default='')
    paid_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    immutable_fields = ('buyer_id', 'checkout_id', 'currency', 'total_amount', 'expires_at')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['checkout'], condition=models.Q(status='pending'), name='payment_pending_checkout'),
            models.CheckConstraint(condition=models.Q(total_amount__gt=0, currency='CNY'), name='payment_positive_cny'),
        ]


class PaymentAllocation(ImmutableSnapshot):
    payment = models.ForeignKey(PaymentOrder, on_delete=models.PROTECT, related_name='allocations')
    order = models.ForeignKey('orders.OrderInfo', on_delete=models.PROTECT, related_name='payment_allocations')
    merchant = models.ForeignKey('users.UserProfile', on_delete=models.PROTECT, related_name='payment_allocations')
    merchant_name = models.CharField(max_length=50, blank=True, default='')
    goods_amount = models.DecimalField(max_digits=12, decimal_places=2)
    freight_amount = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=12, default='pending', choices=[
        ('pending', '待付款'), ('paid', '已付款'), ('review', '待核验')])
    immutable_fields = ('payment_id', 'order_id', 'merchant_id', 'merchant_name', 'goods_amount', 'freight_amount', 'amount')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['payment', 'order'], name='payment_allocation_order'),
            models.CheckConstraint(condition=models.Q(goods_amount__gt=0, freight_amount__gte=0,
                amount=models.F('goods_amount') + models.F('freight_amount')), name='payment_allocation_amount'),
        ]


class PaymentReceipt(models.Model):
    # One unique registry for BOTH combined and original order-number callbacks.
    trade_no = models.CharField(max_length=100, unique=True)
    payment = models.ForeignKey(PaymentOrder, on_delete=models.PROTECT, null=True, blank=True, related_name='receipts')
    legacy_order = models.ForeignKey('orders.OrderInfo', on_delete=models.PROTECT, null=True, blank=True, related_name='payment_receipts')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(max_length=20, default='pending', choices=[
        ('pending', '处理中'), ('paid', '已确认'), ('review', '待核验'), ('legacy_reference', '历史流水引用')])
    review_reason = models.CharField(max_length=80, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=(models.Q(payment__isnull=False, legacy_order__isnull=True) |
                models.Q(payment__isnull=True, legacy_order__isnull=False)), name='payment_receipt_one_target'),
            models.CheckConstraint(condition=(models.Q(outcome='legacy_reference') |
                models.Q(amount__gt=0, currency='CNY', currency__isnull=False,
                         received_at__isnull=False)), name='payment_receipt_verified_fields'),
        ]
