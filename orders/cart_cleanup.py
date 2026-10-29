"""Transactional outbox for Redis cart consumption; MySQL owns task delivery."""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from django_redis import get_redis_connection
from carts.state import CLEAN_SCRIPT
from .models import CartCleanupTask

logger = logging.getLogger(__name__)


def record_cleanup(checkout, snapshots, quantities):
    """Called inside the checkout transaction, with the buyer row locked."""
    from .reservations import ReservationError
    for sid, row in snapshots.items():
        try:
            start, end = int(row['removed']), int(row['added'])
            generation, version = row['generation'], int(row['version'])
            if not isinstance(generation, str) or not 1 <= len(generation) <= 64:
                raise ValueError()
            if not 0 <= start < end <= 2**53-1 or end-start != quantities[sid] or version < 1:
                raise ValueError()
        except (KeyError, TypeError, ValueError):
            raise ReservationError('CART_CHANGED', '采购车已变化，请刷新后重试')
        # Two different request IDs must not purchase the same cart units twice.
        if CartCleanupTask.objects.filter(checkout__user=checkout.user, sku_id=sid,
                                         generation=generation, consumed_to__gt=start).exists():
            raise ReservationError('CART_CHANGED', '采购车正在同步，请刷新后重试')
        CartCleanupTask.objects.create(checkout=checkout, sku_id=sid, generation=generation,
                                       version=version, consumed_from=start, consumed_to=end)


def process_task(task_id, conn):
    with transaction.atomic():
        task = CartCleanupTask.objects.select_for_update().select_related('checkout__user').get(pk=task_id)
        if task.status == 'done':
            return True
        task.attempts += 1
        try:
            result = conn.eval(CLEAN_SCRIPT, 1, 'carts_' + task.checkout.user.username,
                               str(task.sku_id), task.generation, str(task.consumed_to))
            if isinstance(result, bytes): result = result.decode('ascii')
            if result not in ('missing', 'superseded', 'already_applied', 'consumed'):
                raise ValueError('Unexpected cleanup result')
        except Exception as exc:
            task.last_error = type(exc).__name__[:100]
            task.next_attempt_at = timezone.now() + timedelta(seconds=min(300, 2**min(task.attempts, 8)))
            task.save(update_fields=['attempts', 'last_error', 'next_attempt_at'])
            logger.warning('cart.cleanup.retry task=%s reason=%s', task.pk, task.last_error)
            return False
        task.status, task.result, task.last_error = 'done', result, ''
        task.completed_at = timezone.now()
        task.save(update_fields=['attempts', 'status', 'result', 'last_error', 'completed_at'])
        return True


def drain_cleanup(user_id=None, checkout_id=None, conn=None, limit=100, force=False):
    tasks = CartCleanupTask.objects.filter(status='pending')
    if not force: tasks = tasks.filter(next_attempt_at__lte=timezone.now())
    if user_id is not None: tasks = tasks.filter(checkout__user_id=user_id)
    if checkout_id is not None: tasks = tasks.filter(checkout_id=checkout_id)
    ids = list(tasks.order_by('next_attempt_at', 'pk').values_list('pk', flat=True)[:limit])
    if not ids: return 0
    owned = conn is None
    if owned:
        # Bound a disconnected Redis call; do not mutate the shared Django pool.
        from redis import Redis, ConnectionPool
        pool = get_redis_connection('carts').connection_pool
        options = dict(pool.connection_kwargs, socket_connect_timeout=3, socket_timeout=3)
        conn = Redis(connection_pool=ConnectionPool(connection_class=pool.connection_class, **options))
    try:
        return sum(process_task(pk, conn) for pk in ids)
    finally:
        if owned:
            conn.connection_pool.disconnect()


def after_checkout(checkout_id, conn):
    """Callback failures must never turn a committed purchase into an HTTP failure."""
    try:
        drain_cleanup(checkout_id=checkout_id, conn=conn, force=True)
    except Exception:
        logger.exception('cart.cleanup.dispatch_failed checkout=%s', checkout_id)
