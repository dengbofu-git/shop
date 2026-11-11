"""Account-owned purchase signals; never infer dislikes or call a model.

The current completed-order state is reconciled, rather than relying only on
signals or updated_time (bulk state changes may bypass both). All identifiers
in evidence stay in the private, server-side profile queue.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import unicodedata

from django.conf import settings
from django.db import connection, transaction
from django.db.models import Q
from django.utils import timezone

from ai_storage.database import alias
from orders.lifecycle import status_filter
from orders.models import OrderGoods, OrderInfo
from users.models import UserProfile

from .pii import contains_pii


POLICY_VERSION = 'purchase-soft-signals-v1'
WINDOW_DAYS = 180
LARGE_PURCHASE_CNY = Decimal('1000.00')
MAX_ORDERS = 1000
MAX_ITEMS = 10000
MAX_CANDIDATES_PER_TYPE = 20


class BehaviorSnapshotLimit(ValueError):
    """A partial purchase history must not silently replace an existing profile."""


def _enabled():
    return getattr(settings, 'SUPPORT_AUTO_PROFILE_ENABLED', False)


def _now(value):
    value = timezone.now() if value is None else value
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise ValueError('Behavior snapshots need an aware observation time')
    return value


def _owner(value):
    if type(value) is not int or value <= 0:
        raise ValueError('Behavior snapshots need a positive account ID')
    return value


def _term(value):
    value = ' '.join(unicodedata.normalize('NFKC', value or '').split())
    if not value or len(value) > 40 or contains_pii(value) or any(ord(c) < 32 for c in value):
        return None
    return value


def _paid_at(order):
    """Use a recorded payment time, never creation/update/worker time."""
    dates = [order.paid_at] if order.paid_at is not None else []
    if order.order_type == 'presale':
        presale = getattr(order, 'presaleorder', None)
        if presale is None or not presale.deposit_paid or not presale.balance_paid:
            return None
        if presale.balance_pay_time is not None:
            dates.append(presale.balance_pay_time)
    return max(dates) if dates else None


def _weight(groups, net_cny):
    """Amounts and quantity do not create extra independent purchase events."""
    dates = sorted(group['paid_at'] for group in groups)
    count = len(dates)
    span = dates[-1] - dates[0]
    short_repeat = any(timedelta(days=1) <= right-left <= timedelta(days=30)
                       for index, left in enumerate(dates) for right in dates[index+1:])
    if count >= 3 and span >= timedelta(days=14):
        return min(4.0, 3.0 + (count-3)*0.2), 'repeated_purchase'
    if count >= 2 and short_repeat:
        return 1.25, 'short_interval_repeat'
    if count >= 2:
        return .7, 'multiple_purchase_groups'
    if net_cny >= LARGE_PURCHASE_CNY:
        return .35, 'single_large_purchase_weak'
    return .15, 'single_purchase_weak'


def build_behavior_snapshot(owner_id, now=None):
    """Return an authoritative *current* purchase-signal snapshot for one buyer.

    Empty snapshots intentionally invalidate older behavior contributions. Their
    source_at is None: observing a refund does not constitute a new preference.
    A caller processing a queue job must re-read and compare this fingerprint.
    """
    if not _enabled():
        return {'fingerprint': None, 'source_at': None, 'candidates': [],
                'evidence': {'disabled': True}}
    owner_id, now = _owner(owner_id), _now(now)
    if alias() != 'default':
        raise RuntimeError('Automatic purchase profiles require the unified database')
    start = now - timedelta(days=WINDOW_DAYS)
    # Legacy completed orders without a reliable paid timestamp are not guessed.
    recent_payment = (Q(paid_at__gte=start, paid_at__lte=now)
                      | Q(order_type='presale', presaleorder__balance_pay_time__gte=start,
                          presaleorder__balance_pay_time__lte=now))
    eligible = (OrderInfo.objects.filter(user_profile_id=owner_id).filter(status_filter(4))
                .filter(currency='CNY', payment_exception='', closed_at__isnull=True).filter(recent_payment)
                .select_related('checkout_request', 'presaleorder', 'trialorder')
                .order_by('order_id'))
    if connection.in_atomic_block:
        # PostgreSQL must not try to lock the nullable outer-joined subtype rows.
        eligible = eligible.select_for_update(of=('self',))
    orders = list(eligible[:MAX_ORDERS+1])
    if len(orders) > MAX_ORDERS:
        raise BehaviorSnapshotLimit('Purchase history exceeds the bounded automatic profile window')
    accepted = {}
    rejected = defaultdict(int)
    for order in orders:
        paid_at = _paid_at(order)
        if paid_at is None or not start <= paid_at <= now:
            rejected['unreliable_or_outside_window_payment_time'] += 1
            continue
        if order.total_amount <= 0:
            rejected['non_positive_purchase_amount'] += 1
            continue
        if order.checkout_request_id and order.checkout_request.user_id != owner_id:
            rejected['checkout_owner_mismatch'] += 1
            continue
        # Group identity survives merchant splitting and merged payment. Legacy
        # rows with no checkout identity share a local payment day, conservatively.
        key = ('checkout:'+str(order.checkout_request_id) if order.checkout_request_id
               else 'legacy-day:'+timezone.localtime(paid_at).date().isoformat())
        accepted[order.pk] = (order, key, paid_at)
    items = list(OrderGoods.objects.filter(order_info_id__in=accepted)
                 .select_related('sku__spu__catalog', 'sku__spu__brand')
                 .order_by('pk')[:MAX_ITEMS+1])
    if len(items) > MAX_ITEMS:
        raise BehaviorSnapshotLimit('Purchase item history exceeds the automatic profile limit')
    groups = {}
    private_orders = {}
    for item in items:
        order, key, paid_at = accepted[item.order_info_id]
        if item.currency != 'CNY' or item.count <= 0 or item.price <= 0:
            rejected['invalid_or_non_cny_line'] += 1
            continue
        spu = item.sku.spu
        terms = [('category', _term(spu.catalog.name)),
                 ('brand', _term(spu.brand.name) if spu.brand_id else None),
                 ('keyword', _term(spu.name))]
        amount = (item.price*item.count).quantize(Decimal('.01'))
        group = groups.setdefault(key, {'paid_at': paid_at, 'orders': set(),
                                        'terms': {}, 'net_cny': Decimal('0.00')})
        group['paid_at'] = max(group['paid_at'], paid_at)
        group['orders'].add(str(order.pk))
        group['net_cny'] += amount
        private_orders[str(order.pk)] = {'paid_at': paid_at.isoformat(), 'group': key}
        # One term in one checkout is one event even with multiple SKUs,
        # merchants, repeated order lines, or a high purchased quantity.
        for kind, value in terms:
            if value is None:
                continue
            term_key = (kind, value.casefold())
            term = group['terms'].setdefault(term_key, {'type': kind, 'value': value,
                                                       'net_cny': Decimal('0.00'), 'paid_at': paid_at})
            term['net_cny'] += amount
            term['paid_at'] = max(term['paid_at'], paid_at)
    support = defaultdict(list)
    for group_key, group in groups.items():
        for term_key, term in group['terms'].items():
            support[term_key].append({'group': group_key, 'paid_at': term['paid_at'],
                                      'net_cny': term['net_cny'], 'value': term['value']})
    all_candidates = []
    for (kind, normalized), term_groups in sorted(support.items()):
        amount = sum((group['net_cny'] for group in term_groups), Decimal('0.00'))
        weight, reason = _weight(term_groups, amount)
        source_at = max(group['paid_at'] for group in term_groups)
        all_candidates.append({'type': kind, 'value': term_groups[-1]['value'],
            'polarity': 'like', 'scope': 'long_term', 'weight': weight,
            'source_at': source_at.isoformat(),
            'evidence': {'source_type': 'purchase_statistics', 'policy': POLICY_VERSION,
                'window_days': WINDOW_DAYS, 'group_count': len(term_groups),
                'groups': sorted(group['group'] for group in term_groups),
                'span_days': (source_at-min(group['paid_at'] for group in term_groups)).total_seconds()/86400,
                'merchandise_cny': format(amount, '.2f'), 'reason': reason}})
    candidates = []
    for kind in ('category', 'brand', 'keyword'):
        candidates.extend(sorted((c for c in all_candidates if c['type'] == kind),
                                  key=lambda c: (-c['weight'], c['value'].casefold()))[:MAX_CANDIDATES_PER_TYPE])
    canonical_groups = [{
        'group': key, 'orders': sorted(group['orders']), 'paid_at': group['paid_at'].isoformat(),
        'net_cny': format(group['net_cny'], '.2f'),
        'terms': [{'type': kind, 'key': normalized, 'value': value['value'],
                   'net_cny': format(value['net_cny'], '.2f'), 'paid_at': value['paid_at'].isoformat()}
                  for (kind, normalized), value in sorted(group['terms'].items())],
    } for key, group in sorted(groups.items())]
    # Do not include observation time: repeated polling must not make new events.
    # Enqueue assigns a transition generation so A->B->A is still observable.
    fingerprint = sha256(json.dumps({'owner_id': owner_id, 'policy': POLICY_VERSION,
        'groups': canonical_groups}, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    return {'fingerprint': fingerprint,
        'source_at': max((group['paid_at'] for group in groups.values()), default=None),
        'candidates': candidates,
        'evidence': {'source_type': 'purchase_statistics', 'policy': POLICY_VERSION,
            'observed_at': now.isoformat(), 'window_days': WINDOW_DAYS,
            'purchase_groups': canonical_groups, 'orders': private_orders,
            'inspected_recent_completed_orders': len(orders), 'rejected': dict(rejected),
            'terms_omitted_by_bound': len(all_candidates)-len(candidates),
            'payment_time_rule': 'recorded_paid_at_or_presale_balance_payment_only',
            'catalog_rule': 'current_sku_spu_tags_not_an_immutable_historical_category'}}


def reconcile_behavior_batch(after_owner_id=0, limit=100, now=None):
    """Sweep buyers with source orders or prior state, including invalidations.

    Repeat from cursor zero after complete=True. This captures cancellations,
    refunds, changed subtype states, time-window expiry and bulk SQL updates.
    """
    if not _enabled():
        return {'cursor': after_owner_id, 'processed': 0, 'queued': 0,
                'complete': True, 'disabled': True}
    if type(after_owner_id) is not int or after_owner_id < 0 or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('Invalid behavior sweep cursor or batch limit')
    now = _now(now)
    if alias() != 'default':
        raise RuntimeError('Automatic purchase profiles require the unified database')
    from ai_storage.models import BuyerMemory
    from ai_storage.profile_models import BuyerPreferenceState
    from ai_storage.profile_service import enqueue_behavior
    # Every behavior admission creates a durable state row. Thus prior behavior
    # owners remain discoverable after invalidation without scanning the growing
    # job history or enrolling chat-only accounts in empty purchase snapshots.
    owners = (OrderInfo.objects.filter(user_profile_id__gt=after_owner_id)
              .values_list('user_profile_id', flat=True).order_by()
              .union(BuyerMemory.objects.filter(owner_id__gt=after_owner_id).values_list('owner_id', flat=True).order_by(),
                     BuyerPreferenceState.objects.filter(owner_id__gt=after_owner_id).values_list('owner_id', flat=True).order_by())
              .order_by('user_profile_id'))
    ids = list(owners[:limit+1])
    queued = processed = 0
    skipped = []
    for owner_id in ids[:limit]:
        try:
            with transaction.atomic():
                user = UserProfile.objects.select_for_update().filter(pk=owner_id, is_active=True, user_type='customer').first()
                if user is None:
                    skipped.append({'owner_id': owner_id, 'code': 'inactive_or_non_buyer'})
                    continue
                snapshot = build_behavior_snapshot(owner_id, now=now)
                outcome = enqueue_behavior(owner_id, snapshot['fingerprint'], snapshot['source_at'],
                                           snapshot['candidates'], evidence=snapshot['evidence'])
                queued += bool(outcome)
                processed += 1
        except BehaviorSnapshotLimit:
            skipped.append({'owner_id': owner_id, 'code': 'snapshot_limit'})
    return {'cursor': ids[min(limit,len(ids))-1] if ids else after_owner_id,
            'processed': processed, 'queued': queued, 'complete': len(ids) <= limit,
            'skipped': skipped}
