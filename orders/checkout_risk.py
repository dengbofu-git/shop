"""Group-based release history and admission cooldowns.

Both public mutating helpers require the caller's buyer row lock and transaction.
Admission returns an error instead of raising: commit this short transaction
before raising the error, or the new cooldown and consumed cursors would vanish.
"""
from datetime import timedelta
from math import ceil

from django.conf import settings
from django.db.models import Count, Max

from .models import ReservationRiskEvent, ReservationRiskState, StockHold


def group_key(order):
    if order.checkout_request_id is not None:
        return 'checkout:%s' % order.checkout_request_id
    return 'order:%s' % order.pk


def record_release(order, reason, now):
    """Record one immutable fact after a real hold release under the buyer lock."""
    kind = {'user_cancel': 'cancel', 'expired': 'timeout'}.get(reason)
    if kind is None or not order.reservation_managed:
        return None
    if not StockHold.objects.filter(item__order_info=order, state='released').exists():
        return None
    event, _ = ReservationRiskEvent.objects.get_or_create(
        user_id=order.user_profile_id, group_key=group_key(order), kind=kind,
        defaults={'occurred_at': now, 'trigger_order': order, 'checkout_id': order.checkout_request_id},
    )
    return event


def _cooldown_error(state, now):
    # Keep reservations free to import these helpers without a module cycle.
    from .reservations import ReservationError
    return ReservationError(
        'RESERVATION_COOLDOWN', '待付款订单取消或超时过于频繁，请在冷却结束后重试', 429,
        retry_after=ceil((state.cooldown_until - now).total_seconds()),
        cooldown_until=state.cooldown_until.isoformat(), cooldown_reason=state.cooldown_kind,
    )


def check_admission(user, now):
    """Return ReservationError/None; NEVER raise for an admission denial.

    The buyer lock serializes state creation, event recording, and admissions.
    Only fresh events after the consumed cursor within (now - 1h, now] count.
    An active cooldown is fixed, regardless of retries or additional events.
    """
    state, _ = ReservationRiskState.objects.get_or_create(user=user)
    if state.cooldown_until is not None and state.cooldown_until > now:
        return _cooldown_error(state, now)

    rules = (
        ('timeout', 'RESERVATION_TIMEOUT_GROUPS_PER_HOUR', 3, 'RESERVATION_TIMEOUT_COOLDOWN_SECONDS', 1800),
        ('cancel', 'RESERVATION_CANCEL_GROUPS_PER_HOUR', 5, 'RESERVATION_CANCEL_COOLDOWN_SECONDS', 600),
    )
    for kind, threshold_setting, default_threshold, duration_setting, default_duration in rules:
        cursor_field = kind + '_cursor'
        batch = ReservationRiskEvent.objects.filter(
            user=user, kind=kind, pk__gt=getattr(state, cursor_field),
            occurred_at__gt=now - timedelta(hours=1), occurred_at__lte=now,
        ).aggregate(count=Count('pk'), last=Max('pk'))
        if batch['count'] < getattr(settings, threshold_setting, default_threshold):
            continue
        duration = getattr(settings, duration_setting, default_duration)
        if kind == 'cancel':
            previous = state.last_cancel_cooldown_at
            escalation_window = getattr(settings, 'RESERVATION_CANCEL_ESCALATION_WINDOW_SECONDS', 86400)
            if previous is not None and timedelta(0) <= now - previous < timedelta(seconds=escalation_window):
                duration = getattr(settings, 'RESERVATION_REPEAT_CANCEL_COOLDOWN_SECONDS', 1800)
            state.last_cancel_cooldown_at = now
        setattr(state, cursor_field, batch['last'])
        state.cooldown_until = now + timedelta(seconds=duration)
        state.cooldown_kind = kind
        state.save(update_fields=[cursor_field, 'cooldown_until', 'cooldown_kind', 'last_cancel_cooldown_at'])
        return _cooldown_error(state, now)
    return None
