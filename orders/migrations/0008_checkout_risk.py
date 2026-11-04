"""Persist group risk facts, conservatively recovering only proven releases."""
from django.db import migrations, models
from django.db.models import F
from django.utils import timezone
import django.db.models.deletion


def backfill_events(apps, schema_editor):
    alias = schema_editor.connection.alias
    Hold = apps.get_model('orders', 'StockHold')
    Event = apps.get_model('orders', 'ReservationRiskEvent')
    cutoff = timezone.now()
    # A closed order alone is not release evidence. Unknown, inconsistent, and
    # future timestamps are excluded rather than turned into buyer penalties.
    rows = Hold.objects.using(alias).filter(
        state='released', released_at__isnull=False,
        item__order_info__reservation_managed=True,
        item__order_info__status=0,
        item__order_info__close_reason__in=['user_cancel', 'expired'],
        item__order_info__closed_at__isnull=False,
        released_at__gte=F('item__order_info__created_time'),
        released_at__lte=F('item__order_info__closed_at'),
        item__order_info__closed_at__lte=cutoff,
    ).values(
        'item__order_info_id', 'item__order_info__user_profile_id',
        'item__order_info__checkout_request_id', 'item__order_info__closed_at',
        'item__order_info__close_reason',
    ).order_by('item__order_info__closed_at', 'item__order_info_id').distinct()
    for row in rows.iterator(chunk_size=1000):
        checkout_id = row['item__order_info__checkout_request_id']
        order_id = row['item__order_info_id']
        key = 'checkout:%s' % checkout_id if checkout_id is not None else 'order:%s' % order_id
        Event.objects.using(alias).get_or_create(
            user_id=row['item__order_info__user_profile_id'], group_key=key,
            kind='cancel' if row['item__order_info__close_reason'] == 'user_cancel' else 'timeout',
            defaults={'occurred_at': row['item__order_info__closed_at'],
                      'trigger_order_id': order_id, 'checkout_id': checkout_id},
        )


class Migration(migrations.Migration):
    dependencies = [('orders', '0007_order_currency_snapshot')]
    operations = [
        migrations.CreateModel(
            name='ReservationRiskEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('group_key', models.CharField(max_length=80)),
                ('kind', models.CharField(choices=[('timeout', '超时释放'), ('cancel', '买家取消')], max_length=12)),
                ('occurred_at', models.DateTimeField()),
                ('checkout', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='orders.checkoutrequest')),
                ('trigger_order', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='orders.orderinfo')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='users.userprofile')),
            ],
            options={
                'indexes': [models.Index(fields=['user', 'kind', 'occurred_at'], name='reservation_risk_window')],
                'constraints': [models.UniqueConstraint(fields=['user', 'group_key', 'kind'], name='reservation_risk_group_kind')],
            },
        ),
        migrations.CreateModel(
            name='ReservationRiskState',
            fields=[
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, primary_key=True, serialize=False, to='users.userprofile')),
                ('cooldown_until', models.DateTimeField(blank=True, null=True)),
                ('cooldown_kind', models.CharField(blank=True, default='', max_length=12)),
                ('timeout_cursor', models.PositiveBigIntegerField(default=0)),
                ('cancel_cursor', models.PositiveBigIntegerField(default=0)),
                ('last_cancel_cooldown_at', models.DateTimeField(blank=True, null=True)),
            ],
        ),
        migrations.RunPython(backfill_events, reverse_code=migrations.RunPython.noop),
    ]
