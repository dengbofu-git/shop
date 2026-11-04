"""Create payment attempts; historical trade numbers remain references only."""
import django.db.models.deletion
from django.db import migrations, models
import pays.models


def register_legacy_references(apps, schema_editor):
    alias = schema_editor.connection.alias
    Order = apps.get_model('orders', 'OrderInfo')
    Receipt = apps.get_model('pays', 'PaymentReceipt')
    rows = Order.objects.using(alias).exclude(payment_trade_no__isnull=True).exclude(payment_trade_no='')
    for order in rows.iterator(chunk_size=1000):
        Receipt.objects.using(alias).create(
            trade_no=order.payment_trade_no, legacy_order_id=order.pk,
            amount=order.total_amount, currency=order.currency,
            received_at=None, outcome='legacy_reference')


class Migration(migrations.Migration):
    initial = True
    dependencies = [('orders', '0008_checkout_risk')]
    operations = [
        migrations.CreateModel(
            name='PaymentOrder',
            fields=[
                ('payment_id', models.CharField(default=pays.models.payment_id, editable=False, max_length=36, primary_key=True, serialize=False)),
                ('currency', models.CharField(default='CNY', max_length=3)),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('expires_at', models.DateTimeField()),
                ('status', models.CharField(choices=[('pending', '待付款'), ('paid', '已付款'), ('invalid', '已失效'), ('review', '待核验')], default='pending', max_length=12)),
                ('payment_exception', models.CharField(blank=True, default='', max_length=80)),
                ('paid_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('buyer', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='checkout_payments', to='users.userprofile')),
                ('checkout', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='orders.checkoutrequest')),
            ],
            options={'constraints': [
                models.UniqueConstraint(condition=models.Q(status='pending'), fields=('checkout',), name='payment_pending_checkout'),
                models.CheckConstraint(condition=models.Q(total_amount__gt=0, currency='CNY'), name='payment_positive_cny'),
            ]},
        ),
        migrations.CreateModel(
            name='PaymentAllocation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('merchant_name', models.CharField(blank=True, default='', max_length=50)),
                ('goods_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('freight_amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('status', models.CharField(choices=[('pending', '待付款'), ('paid', '已付款'), ('review', '待核验')], default='pending', max_length=12)),
                ('merchant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payment_allocations', to='users.userprofile')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payment_allocations', to='orders.orderinfo')),
                ('payment', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='allocations', to='pays.paymentorder')),
            ],
            options={'constraints': [
                models.UniqueConstraint(fields=('payment', 'order'), name='payment_allocation_order'),
                models.CheckConstraint(condition=models.Q(goods_amount__gt=0, freight_amount__gte=0,
                    amount=models.F('goods_amount') + models.F('freight_amount')), name='payment_allocation_amount'),
            ]},
        ),
        migrations.CreateModel(
            name='PaymentReceipt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('trade_no', models.CharField(max_length=100, unique=True)),
                ('amount', models.DecimalField(decimal_places=2, max_digits=12)),
                ('currency', models.CharField(blank=True, max_length=3, null=True)),
                ('received_at', models.DateTimeField(blank=True, null=True)),
                ('outcome', models.CharField(choices=[('pending', '处理中'), ('paid', '已确认'), ('review', '待核验'), ('legacy_reference', '历史流水引用')], default='pending', max_length=20)),
                ('review_reason', models.CharField(blank=True, default='', max_length=80)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('legacy_order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='payment_receipts', to='orders.orderinfo')),
                ('payment', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='receipts', to='pays.paymentorder')),
            ],
            options={'constraints': [
                models.CheckConstraint(condition=(models.Q(payment__isnull=False, legacy_order__isnull=True) |
                    models.Q(payment__isnull=True, legacy_order__isnull=False)), name='payment_receipt_one_target'),
                models.CheckConstraint(condition=(models.Q(outcome='legacy_reference') |
                    models.Q(amount__gt=0, currency='CNY', currency__isnull=False,
                             received_at__isnull=False)), name='payment_receipt_verified_fields'),
            ]},
        ),
        migrations.RunPython(register_legacy_references, reverse_code=migrations.RunPython.noop),
    ]
