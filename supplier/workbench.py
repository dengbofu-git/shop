"""Read-only merchant tasks and activity, derived only from persisted records."""
from django.db.models import Exists, F, OuterRef, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from engagement.models import Message
from logistics.models import ShippingOrder
from orders.models import OrderGoods, OrderInfo
from users.access import account_access
from users.decorators import get_user_from_request
from .models import SupplierSettlement


def owned_items(user):
    # A recorded seller takes precedence over today's product owner. Legacy
    # unsnapshotted lines follow the existing merchant order-list visibility.
    return Q(merchant_snapshot=user) | Q(merchant_snapshot__isnull=True, sku__spu__merchant=user)


def waiting_shipment():
    return (Q(order_type='standard', status=2)
            | Q(order_type='trial', trialorder__status=2)
            | Q(order_type='presale', presaleorder__status=4,
                presaleorder__deposit_paid=True, presaleorder__balance_paid=True))


def build_workbench_feed(user):
    ownership = owned_items(user)
    lines = OrderGoods.objects.filter(ownership)
    orders = OrderInfo.objects.filter(pk__in=lines.values('order_info_id'))
    incoming = Message.objects.filter(conversation__merchant=user, conversation__merchant_hidden=False,
                                      sender_id=F('conversation__buyer_id'))
    unread = incoming.filter(id__gt=F('conversation__merchant_read_id'))
    counts = {
        'unshipped': orders.filter(waiting_shipment()).count(),
        'settlement': SupplierSettlement.objects.filter(supplier=user, status='pending').count(),
        'consultations': unread.values('conversation_id').distinct().count(),
        # TODO: no persisted product-approval workflow exists. Never infer
        # approval from is_launched or replace missing data with a fake zero.
        'product_review': None,
        # TODO: trial return states are not independent after-sales tickets.
        # Integrate only after a real application/processing model is available.
        'after_sales': None,
    }
    messages = []
    for message in incoming.order_by('-created_at', '-id')[:4]:
        messages.append({
            'id': 'inquiry:%s' % message.pk, 'kind': 'inquiry',
            'text': message.text[:160], 'created_at': message.created_at.isoformat(),
            'panel': 'merchant_messages.html?conversation_id=%s' % message.conversation_id,
        })
    for order in orders.select_related('trialorder', 'presaleorder').order_by('-updated_time', '-order_id')[:5]:
        detail = getattr(order, 'trialorder', None) if order.order_type == 'trial' else (
            getattr(order, 'presaleorder', None) if order.order_type == 'presale' else order)
        status = detail.status if detail is not None else None
        messages.append({
            'id': 'order:%s' % order.pk, 'kind': 'order', 'order_id': order.pk,
            'order_type': order.order_type, 'status': status,
            'created_at': order.updated_time.isoformat(), 'panel': 'merchant_orders.html',
        })
    # A shared historical order's logistics entry cannot identify which shop
    # actually shipped. Exclude those records rather than attribute them by guess.
    foreign = OrderGoods.objects.filter(order_info_id=OuterRef('pk')).exclude(ownership)
    single_shop = orders.annotate(has_foreign=Exists(foreign)).filter(has_foreign=False)
    shipments = ShippingOrder.objects.filter(order_info_id__in=single_shop.values('pk'))
    for shipment in shipments.order_by('-updated_time', '-id')[:4]:
        messages.append({
            'id': 'shipping:%s' % shipment.pk, 'kind': 'shipping',
            'order_id': shipment.order_info_id, 'tracking_number': shipment.tracking_number,
            'status': shipment.status, 'created_at': shipment.updated_time.isoformat(),
            'panel': 'merchant_orders.html',
        })
    messages.sort(key=lambda row: (row['created_at'], row['id']), reverse=True)
    return {
        'todos': counts, 'total': sum(n for n in counts.values() if n is not None),
        'unavailable': ['product_review', 'after_sales'],
        'messages': messages[:8], 'generated_at': timezone.now().isoformat(),
        'basis': 'Current merchant records; all pending tasks, not the analytics date range. '
                 'Order and shipping times are record-update times, not fabricated notification events.',
    }


@never_cache
def workbench_feed(request):
    if request.method != 'GET':
        response = JsonResponse({'code': 405, 'error': '仅支持读取'}, status=405)
        response['Allow'] = 'GET'
        return response
    user, error = get_user_from_request(request)
    if error is not None or not user.is_active:
        return JsonResponse({'code': 401, 'error': '请先登录有效账号'}, status=401)
    if account_access(user)['redirect_url'] != '/merchant_dashboard.html':
        return JsonResponse({'code': 403, 'error': '需要商家账号'}, status=403)
    return JsonResponse({'code': 200, 'data': build_workbench_feed(user)})
