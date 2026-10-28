"""Shared authorization, historical ownership and public projections."""
import hashlib
import json
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ObjectDoesNotExist
from django.db.models import Avg, Count

from goods.models import SKU, SPU
from orders.models import OrderGoods
from users.access import account_access
from users.models import UserProfile
from .models import Conversation, Review


class APIError(Exception):
    def __init__(self, code, message, status=400):
        self.code, self.message, self.status = code, message, status


def portal(user):
    destination = account_access(user)['redirect_url']
    if destination == '/merchant_dashboard.html':
        return 'merchant'
    if destination == '/buyer_dashboard.html':
        return 'buyer'
    return 'platform'


def integer(value, name='id', default=None):
    if value is None and default is not None:
        return default
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit() or len(str(value)) > 18:
        raise APIError('INVALID_PARAMETER', name + ' 必须是正整数')
    number = int(value)
    if number < 1:
        raise APIError('INVALID_PARAMETER', name + ' 必须是正整数')
    return number


def content(value, minimum=1, maximum=2000):
    if not isinstance(value, str) or not minimum <= len(value.strip()) <= maximum:
        raise APIError('INVALID_TEXT', '文字长度应为 %s～%s 字' % (minimum, maximum))
    return value.strip()


def find(query, **lookup):
    value = query.filter(**lookup).first()
    if value is None:
        raise APIError('NOT_FOUND', '记录不存在或不可访问', 404)
    return value


def participants(user):
    return Conversation.objects.filter(**{portal(user): user})


def visible_conversations(user):
    return participants(user).filter(**{portal(user) + '_hidden': False})


def completed(order):
    if order.order_type == 'standard':
        return order.status == 4
    try:
        if order.order_type == 'trial':
            return order.trialorder.status == 8
        if order.order_type == 'presale':
            detail = order.presaleorder
            return detail.status == 6 and detail.deposit_paid and detail.balance_paid
    except ObjectDoesNotExist:
        pass
    return False


def verified_item(item):
    snap = item.purchase_snapshot
    return bool(item.merchant_snapshot_id and isinstance(snap, dict) and snap.get('origin') == 'purchase'
                and snap.get('merchant_id') == item.merchant_snapshot_id
                and snap.get('sku_id') == item.sku_id and snap.get('spu_id') == item.sku.spu_id)


def review_state(item):
    review = getattr(item, 'review', None)
    reason = None
    if review:
        reason = 'ALREADY_REVIEWED'
    elif not completed(item.order_info):
        reason = 'ORDER_NOT_COMPLETED'
    elif not verified_item(item):
        reason = 'HISTORY_NOT_VERIFIED'
    return {'can_review': reason is None, 'review_id': review.pk if review else None,
            'review_reason': reason}


def item_row(item):
    snap = item.purchase_snapshot or {}
    return dict(review_state(item), id=item.pk, order_id=item.order_info_id,
                sku_id=item.sku_id, product_name=snap.get('product_name', item.sku.spu.name),
                specification=snap.get('specification', item.sku.name),
                merchant_name=snap.get('merchant_name', ''),
                merchant_id=item.merchant_snapshot_id, count=item.count,
                order_type=item.order_info.order_type,
                status_text=item.order_info.get_status_display_text(),
                image_url='/v1/goods/sku/%s/image' % item.sku_id)


def target_context(user, data, conversation=None):
    """Resolve all references on the server; never accept an order/merchant card from clients."""
    if data.get('order_item_id') is not None and data.get('sku_id') is not None:
        raise APIError('INVALID_CONTEXT', '一次只能关联一个商品或订单商品')
    card = {}
    if data.get('order_item_id') is not None:
        eligible = OrderGoods.objects.filter(**({'order_info__user_profile': user} if portal(user) == 'buyer'
                                               else {'merchant_snapshot': user}))
        item = find(eligible.select_related('order_info', 'sku__spu'),
                    pk=integer(data['order_item_id']))
        merchant_id = item.merchant_snapshot_id
        if ((portal(user) == 'buyer' and item.order_info.user_profile_id != user.pk) or
                (portal(user) == 'merchant' and merchant_id != user.pk) or
                (conversation and item.order_info.user_profile_id != conversation.buyer_id)):
            raise APIError('NOT_FOUND', '记录不存在或不可访问', 404)
        if not verified_item(item):
            raise APIError('HISTORY_NOT_VERIFIED', '历史订单缺少可信商家快照，请从店铺发起普通咨询', 409)
        card = {'type': 'order', 'order_id': item.order_info_id, 'order_item_id': item.pk,
                'sku_id': item.sku_id, 'product_name': item.purchase_snapshot['product_name'],
                'specification': item.purchase_snapshot['specification']}
    elif data.get('sku_id') is not None:
        sku = find(SKU.objects.select_related('spu__merchant'), pk=integer(data['sku_id']))
        merchant_id = sku.spu.merchant_id
        card = {'type': 'product', 'sku_id': sku.pk, 'product_name': sku.spu.name,
                'specification': sku.name}
    else:
        merchant_id = conversation.merchant_id if conversation else integer(data.get('merchant_id'), 'merchant_id')
    if conversation and merchant_id != conversation.merchant_id:
        raise APIError('INVALID_CONTEXT', '不能将其他店铺的商品或订单加入本会话', 409)
    merchant = find(UserProfile.objects.all(), pk=merchant_id)
    if not merchant.is_active or portal(merchant) != 'merchant':
        raise APIError('MERCHANT_UNAVAILABLE', '该商家当前无法接收咨询', 409)
    if data.get('merchant_id') is not None and integer(data['merchant_id']) != merchant_id:
        raise APIError('INVALID_CONTEXT', '商品与商家不匹配', 409)
    return merchant, card


def fingerprint(text, data):
    references = {k: str(data[k]) for k in ('sku_id', 'order_item_id', 'merchant_id') if data.get(k) is not None}
    return hashlib.sha256(json.dumps([text, references], sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def message_row(message, user):
    return {'id': message.pk, 'text': message.text, 'context': message.context,
            'is_mine': message.sender_id == user.pk, 'created_at': message.created_at.isoformat(),
            'request_id': message.request_id if message.sender_id == user.pk else None}


def public_review(review):
    name = review.buyer.username
    reply = getattr(review, 'reply', None)
    return {'id': review.pk, 'buyer_name': name[:1] + '***',
            'rating': review.rating, 'text': review.text,
            'specification': review.purchase_snapshot.get('specification', ''),
            'created_at': review.created_at.isoformat(),
            'reply': {'text': reply.text, 'created_at': reply.created_at.isoformat()} if reply else None}


def summary(rows):
    totals = rows.aggregate(total=Count('id'), average=Avg('rating'))
    distribution = {str(n): 0 for n in range(1, 6)}
    for row in rows.values('rating').annotate(count=Count('id')).order_by():
        distribution[str(row['rating'])] = row['count']
    average = float(Decimal(str(totals['average'])).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)) if totals['total'] else None
    return {'total': totals['total'], 'average': average,
            'distribution': distribution}


def sync_counts(spu_id, sku_id):
    # Caller locks the SPU. The review table, not legacy counters, is authoritative.
    SPU.objects.filter(pk=spu_id).update(comments=Review.objects.filter(spu_id=spu_id, is_visible=True).count())
    SKU.objects.filter(pk=sku_id).update(comments=Review.objects.filter(sku_id=sku_id, is_visible=True).count())
