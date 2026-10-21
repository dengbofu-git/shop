import json
import re
from functools import wraps

from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, F, Q
from django.http import JsonResponse
from django.utils import timezone

from goods.models import SKU, SPU
from orders.models import OrderGoods, OrderInfo
from users.decorators import get_user_from_request, platform_permission_required
from users.models import UserProfile
from .models import Conversation, Message, Review, ReviewModeration, ReviewReply, ReviewReport
from .services import (APIError, completed, content, find, fingerprint, integer, item_row,
                       message_row, participants, portal, public_review, review_state,
                       summary, sync_counts, target_context)


def api(methods, roles=()):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            try:
                if request.method not in methods:
                    response = JsonResponse({'code': 405, 'error_code': 'METHOD_NOT_ALLOWED', 'error': '不支持的请求方法'}, status=405)
                    response['Allow'] = ', '.join(methods)
                else:
                    if roles:
                        user, error = get_user_from_request(request)
                        if error is not None:
                            error['Cache-Control'] = 'no-store'
                            return error
                        if not user.is_active:
                            raise APIError('ACCOUNT_INACTIVE', '账号已停用', 401)
                        if portal(user) not in roles:
                            raise APIError('FORBIDDEN', '无权使用此功能', 403)
                        request.user_profile = user
                    if request.method in ('POST', 'PUT'):
                        if len(request.body) > 20000:
                            raise APIError('PAYLOAD_TOO_LARGE', '提交内容过大', 413)
                        try:
                            request.data = json.loads(request.body)
                        except (ValueError, UnicodeDecodeError):
                            raise APIError('INVALID_JSON', '请求格式错误')
                        if not isinstance(request.data, dict):
                            raise APIError('INVALID_JSON', '请求必须为对象')
                    response = view(request, *args, **kwargs)
            except APIError as error:
                response = JsonResponse({'code': error.status, 'error_code': error.code, 'error': error.message}, status=error.status)
            response['Cache-Control'] = 'no-store'
            return response
        return wrapped
    return decorate


def ok(data, status=200):
    return JsonResponse({'code': 200, 'data': data}, status=status)


def page_rows(request, rows, serialize):
    page = Paginator(rows, 20).get_page(integer(request.GET.get('page'), 'page', 1))
    return {'items': [serialize(row) for row in page], 'page': page.number,
            'pages': page.paginator.num_pages, 'total': page.paginator.count}


@api(['GET'], ['buyer', 'merchant'])
def identity(request):
    return ok({'portal': portal(request.user_profile)})


@api(['GET'], ['buyer'])
def resolve(request):
    merchant, card = target_context(request.user_profile, request.GET)
    conv = Conversation.objects.filter(buyer=request.user_profile, merchant=merchant).first()
    return ok({'conversation_id': conv.pk if conv else None,
               'merchant_id': merchant.pk, 'merchant_name': merchant.shop_name or '商家店铺', 'context': card})


def conversation_row(conv, user):
    side = 'buyer' if user.pk == conv.buyer_id else 'merchant'
    other = conv.merchant if side == 'buyer' else conv.buyer
    last = conv.messages.order_by('-id').first()
    return {'id': conv.pk, 'name': (other.shop_name or '商家店铺') if side == 'buyer' else other.username[:1] + '***',
            'last_text': last.text if last else '', 'updated_at': conv.updated_at.isoformat(),
            'unread': conv.messages.filter(id__gt=getattr(conv, side + '_read_id')).exclude(sender=user).count(),
            'other_read_id': conv.merchant_read_id if side == 'buyer' else conv.buyer_read_id}


@api(['GET', 'POST'], ['buyer', 'merchant'])
def conversations(request):
    user = request.user_profile
    if request.method == 'GET':
        rows = participants(user).select_related('buyer', 'merchant')
        result = page_rows(request, rows, lambda row: conversation_row(row, user))
        read_field = 'conversation__' + portal(user) + '_read_id'
        result['unread_total'] = Message.objects.filter(conversation__in=rows, id__gt=F(read_field)).exclude(sender=user).count()
        return ok(result)
    if portal(user) != 'buyer':
        raise APIError('FORBIDDEN', '商家请在已有会话中回复', 403)
    with transaction.atomic():
        # Serialize first-message creation and sender request ids across conversations.
        UserProfile.objects.select_for_update().get(pk=user.pk)
        merchant, _ = target_context(user, request.data)
        conv, _ = Conversation.objects.get_or_create(buyer=user, merchant=merchant)
        return send_message(request, conv)


def send_message(request, conv):
    user, data = request.user_profile, request.data
    text = content(data.get('text'))
    request_id = data.get('request_id')
    if not isinstance(request_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,80}', request_id):
        raise APIError('INVALID_REQUEST_ID', '请提供有效发送标识')
    digest = fingerprint(text, data)
    existing = Message.objects.filter(sender=user, request_id=request_id).first()
    if existing:
        if existing.conversation_id != conv.pk or existing.fingerprint != digest:
            raise APIError('REQUEST_CONFLICT', '相同发送标识不能用于不同消息', 409)
        return ok({'conversation_id': conv.pk, 'message': message_row(existing, user)})
    merchant, card = target_context(user, data, conv)
    if not conv.buyer.is_active or portal(conv.buyer) != 'buyer':
        raise APIError('BUYER_UNAVAILABLE', '该买家当前无法接收消息', 409)
    # Small per-sender limit, enforced under the sender row lock; retries do not count.
    if Message.objects.filter(sender=user, created_at__gte=timezone.now() - timezone.timedelta(minutes=1)).count() >= 30:
        raise APIError('RATE_LIMITED', '发送过于频繁，请稍后重试', 429)
    message = Message.objects.create(conversation=conv, sender=user, text=text, context=card,
                                     request_id=request_id, fingerprint=digest)
    Conversation.objects.filter(pk=conv.pk).update(updated_at=message.created_at)
    return ok({'conversation_id': conv.pk, 'message': message_row(message, user)}, 201)


@api(['GET', 'POST'], ['buyer', 'merchant'])
def messages(request, conversation_id):
    user = request.user_profile
    if request.method == 'POST':
        with transaction.atomic():
            UserProfile.objects.select_for_update().get(pk=user.pk)
            conv = find(participants(user).select_for_update(), pk=conversation_id)
            return send_message(request, conv)
    conv = find(participants(user), pk=conversation_id)
    after, before = request.GET.get('after'), request.GET.get('before')
    if after is not None and before is not None:
        raise APIError('INVALID_CURSOR', '不能同时指定前后游标')
    rows = conv.messages.all()
    if after is not None:
        rows = rows.filter(pk__gt=integer(after, 'after')).order_by('id')
    else:
        if before is not None:
            rows = rows.filter(pk__lt=integer(before, 'before'))
        rows = rows.order_by('-id')
    batch = list(rows[:31]); more = len(batch) > 30
    batch = batch[:30]
    if after is None:
        batch.reverse()
    return ok({'items': [message_row(m, user) for m in batch], 'has_more': more,
               'other_read_id': conv.merchant_read_id if user.pk == conv.buyer_id else conv.buyer_read_id})


@api(['POST'], ['buyer', 'merchant'])
def read_messages(request, conversation_id):
    with transaction.atomic():
        conv = find(participants(request.user_profile).select_for_update(), pk=conversation_id)
        upto = integer(request.data.get('message_id'), 'message_id')
        find(conv.messages.all(), pk=upto)
        field = ('buyer' if request.user_profile.pk == conv.buyer_id else 'merchant') + '_read_id'
        Conversation.objects.filter(pk=conv.pk, **{field + '__lt': upto}).update(**{field: upto})
    return ok({})


@api(['GET'], ['buyer'])
def reviewable_items(request):
    rows = OrderGoods.objects.filter(order_info__user_profile=request.user_profile).select_related(
        'order_info__trialorder', 'order_info__presaleorder', 'sku__spu', 'review')
    if request.GET.get('order_item_id'):
        rows = rows.filter(pk=integer(request.GET['order_item_id']))
    else:
        rows = rows.filter(order_info__buyer_hidden=False)
    if request.GET.get('order_id'):
        rows = rows.filter(order_info_id=request.GET['order_id'])
    if request.GET.get('pending') == '1':
        rows = rows.filter(review__isnull=True).filter(
            Q(order_info__order_type='standard', order_info__status=4) |
            Q(order_info__order_type='trial', order_info__trialorder__status=8) |
            Q(order_info__order_type='presale', order_info__presaleorder__status=6,
              order_info__presaleorder__deposit_paid=True, order_info__presaleorder__balance_paid=True))
    return ok(page_rows(request, rows.order_by('-order_info__created_time', '-id'), item_row))


@api(['POST'], ['buyer'])
def create_review(request):
    data, user = request.data, request.user_profile
    rating = data.get('rating')
    if type(rating) is not int or rating not in range(1, 6):
        raise APIError('INVALID_RATING', '请选择 1～5 星')
    text = content(data.get('text'), 5, 1000)
    item_id = integer(data.get('order_item_id'), 'order_item_id')
    with transaction.atomic():
        # Lock the order first, also shared with hide/delete. Avoid MySQL nullable-join locks.
        owned = find(OrderGoods.objects.filter(order_info__user_profile=user), pk=item_id)
        order = OrderInfo.objects.select_for_update().get(pk=owned.order_info_id)
        item = OrderGoods.objects.select_for_update().get(pk=item_id)
        item.order_info = order
        old = Review.objects.filter(order_item=item).first()
        if old:
            if old.rating == rating and old.text == text:
                return ok({'id': old.pk, 'is_visible': old.is_visible})
            raise APIError('ALREADY_REVIEWED', '该订单商品已经评价', 409)
        state = review_state(item)
        if not state['can_review']:
            raise APIError(state['review_reason'], '订单尚未完成或缺少可信购买快照', 409)
        SPU.objects.select_for_update().get(pk=item.sku.spu_id)
        review = Review.objects.create(order_item=item, buyer=user, merchant_id=item.merchant_snapshot_id,
                                       sku=item.sku, spu=item.sku.spu, purchase_snapshot=item.purchase_snapshot,
                                       rating=rating, text=text)
        sync_counts(review.spu_id, review.sku_id)
    return ok({'id': review.pk, 'is_visible': True}, 201)


@api(['GET'])
def product_reviews(request, sku_id):
    sku = find(SKU.objects.select_related('spu'), pk=sku_id)
    rows = Review.objects.filter(spu_id=sku.spu_id, merchant_id=sku.spu.merchant_id,
                                 is_visible=True).select_related('buyer', 'reply')
    if request.GET.get('scope', 'all') not in ('all', 'sku'):
        raise APIError('INVALID_PARAMETER', '不支持的规格筛选')
    if request.GET.get('scope') == 'sku':
        rows = rows.filter(sku_id=sku.pk)
    sort = request.GET.get('sort', 'latest')
    ordering = {'latest': ['-created_at', '-id'], 'rating_desc': ['-rating', '-id'], 'rating_asc': ['rating', '-id']}
    if sort not in ordering:
        raise APIError('INVALID_PARAMETER', '不支持的排序')
    result = page_rows(request, rows.order_by(*ordering[sort]), public_review)
    result['summary'] = summary(rows)
    return ok(result)


@api(['GET'], ['buyer', 'merchant'])
def own_reviews(request):
    user = request.user_profile
    rows = Review.objects.filter(**{portal(user): user}).select_related('buyer', 'reply')
    if request.GET.get('rating'):
        rows = rows.filter(rating=integer(request.GET['rating'], 'rating'))
    if request.GET.get('sku_id'):
        rows = rows.filter(sku_id=integer(request.GET['sku_id']))
    query = request.GET.get('q', '').strip()[:200]
    if query:
        rows = rows.filter(Q(text__icontains=query) | Q(sku__name__icontains=query) | Q(spu__name__icontains=query))
    if request.GET.get('unreplied') == '1':
        rows = rows.filter(reply__isnull=True)
    def row(review):
        return dict(public_review(review), is_visible=review.is_visible,
                    product_name=review.purchase_snapshot.get('product_name', ''), sku_id=review.sku_id)
    return ok(page_rows(request, rows, row))


@api(['POST'], ['merchant'])
def reply_review(request, review_id):
    text = content(request.data.get('text'), 1, 1000)
    with transaction.atomic():
        review = find(Review.objects.select_for_update(), pk=review_id, merchant=request.user_profile)
        if not review.is_visible:
            raise APIError('REVIEW_HIDDEN', '该评价当前不公开', 409)
        reply = getattr(review, 'reply', None)
        if reply:
            if reply.text == text:
                return ok({'id': reply.pk})
            raise APIError('ALREADY_REPLIED', '该评价已经回复', 409)
        reply = ReviewReply.objects.create(review=review, author=request.user_profile, text=text)
    return ok({'id': reply.pk}, 201)


@api(['POST'], ['buyer', 'merchant'])
def report_review(request, review_id):
    reason = content(request.data.get('reason'), 5, 500)
    query = Review.objects.all()
    if portal(request.user_profile) == 'merchant':
        query = query.filter(merchant=request.user_profile)
    else:
        query = query.filter(is_visible=True)
    review = find(query, pk=review_id)
    report, created = ReviewReport.objects.get_or_create(review=review, reporter=request.user_profile,
                                                        defaults={'reason': reason})
    return ok({'id': report.pk}, 201 if created else 200)


@platform_permission_required('goods_manage')
@api(['GET'])
def moderation_list(request):
    rows = Review.objects.select_related('buyer', 'reply').annotate(report_count=Count('reports')).order_by('-created_at', '-id')
    if request.GET.get('rating'):
        rows = rows.filter(rating=integer(request.GET['rating'], 'rating'))
    if request.GET.get('q'):
        needle = request.GET['q'].strip()[:200]
        rows = rows.filter(Q(text__icontains=needle) | Q(sku__name__icontains=needle) | Q(spu__name__icontains=needle))
    if request.GET.get('reported') == '1':
        rows = rows.filter(report_count__gt=0)
    def row(review):
        result = dict(public_review(review), is_visible=review.is_visible, report_count=review.report_count,
                      product_name=review.purchase_snapshot.get('product_name', ''))
        result['reports'] = list(review.reports.order_by('-id').values('id', 'reason', 'created_at')[:20])
        result['moderations'] = list(review.moderations.order_by('-id').values('id', 'is_visible', 'reason', 'created_at')[:10])
        return result
    return ok(page_rows(request, rows, row))


@platform_permission_required('goods_manage')
@api(['POST'])
def moderate_review(request, review_id):
    reason = content(request.data.get('reason'), 5, 500)
    visible = request.data.get('is_visible')
    if type(visible) is not bool:
        raise APIError('INVALID_PARAMETER', '请指定评价公开状态')
    with transaction.atomic():
        review = find(Review.objects.select_for_update(), pk=review_id)
        SPU.objects.select_for_update().get(pk=review.spu_id)
        if review.is_visible != visible:
            ReviewModeration.objects.create(review=review, actor=request.user_profile,
                was_visible=review.is_visible, is_visible=visible, reason=reason)
            review.is_visible = visible
            review.save(update_fields=['is_visible'])
            sync_counts(review.spu_id, review.sku_id)
    return ok({'id': review.pk, 'is_visible': visible})
