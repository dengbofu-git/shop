"""Private buyer favorites and browsing history; identity comes only from JWT."""
from functools import wraps

from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone

from users.decorators import get_user_from_request
from users.models import UserProfile
from .models import BrowsingHistory, Favorite, SKU

HISTORY_LIMIT = 100
PAGE_SIZE = 12


def buyer_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user, error = get_user_from_request(request)
        if error is not None:
            return error
        if not user.is_active:
            return JsonResponse({'code': 401, 'error': '账号未激活或已停用'}, status=401)
        if not user.is_customer():
            return JsonResponse({'code': 403, 'error': '只有买家可以访问此功能'}, status=403)
        request.user_profile = user
        response = view(request, *args, **kwargs)
        response['Cache-Control'] = 'no-store'
        return response
    return wrapped


def method_error(allowed):
    response = JsonResponse({'code': 405, 'error': '不支持的请求方法'}, status=405)
    response['Allow'] = ', '.join(allowed)
    return response


def list_records(request, model):
    try:
        page_number = int(request.GET.get('page', '1'))
        if page_number < 1:
            raise ValueError
    except (ValueError, TypeError):
        return JsonResponse({'code': 400, 'error': 'page 必须是正整数'}, status=400)
    records = model.objects.filter(user=request.user_profile).select_related('sku__spu')
    pages = Paginator(records, PAGE_SIZE)
    page = pages.get_page(page_number)
    favorite_ids = set(Favorite.objects.filter(
        user=request.user_profile, sku_id__in=[row.sku_id for row in page]
    ).values_list('sku_id', flat=True))
    data = []
    for row in page:
        sku = row.sku
        timestamp = row.created_time if model is Favorite else row.viewed_time
        data.append({
            'skuid': sku.id, 'product_name': sku.spu.name, 'name': sku.name,
            'caption': sku.caption, 'price': str(sku.price),
            'image_url': f'/v1/goods/sku/{sku.id}/image',
            'is_launched': sku.is_launched, 'is_favorite': sku.id in favorite_ids,
            'recorded_at': timestamp.isoformat(),
        })
    return JsonResponse({'code': 200, 'data': data, 'paginator': {
        'page': page.number, 'pages': pages.num_pages, 'pagesize': PAGE_SIZE,
        'total': pages.count,
    }})


@buyer_only
def favorites(request):
    if request.method != 'GET':
        return method_error(['GET'])
    return list_records(request, Favorite)


@buyer_only
def favorite(request, sku_id):
    if request.method not in ('GET', 'PUT', 'DELETE'):
        return method_error(['GET', 'PUT', 'DELETE'])
    own = Favorite.objects.filter(user=request.user_profile, sku_id=sku_id)
    if request.method == 'DELETE':
        own.delete()
        return JsonResponse({'code': 200, 'data': {'is_favorite': False}})
    if request.method == 'GET':
        return JsonResponse({'code': 200, 'data': {'is_favorite': own.exists()}})
    if not SKU.objects.filter(id=sku_id, is_launched=True).exists():
        return JsonResponse({'code': 404, 'error': '商品不存在或已下架'}, status=404)
    Favorite.objects.get_or_create(user=request.user_profile, sku_id=sku_id)
    return JsonResponse({'code': 200, 'data': {'is_favorite': True}})


@buyer_only
def recent(request):
    if request.method == 'GET':
        return list_records(request, BrowsingHistory)
    if request.method == 'DELETE':
        # Serialize clear/remove/record for one account on databases with row locks.
        with transaction.atomic():
            UserProfile.objects.select_for_update().get(pk=request.user_profile.pk)
            BrowsingHistory.objects.filter(user=request.user_profile).delete()
        return JsonResponse({'code': 200, 'data': {}})
    return method_error(['GET', 'DELETE'])


@buyer_only
def recent_item(request, sku_id):
    if request.method not in ('POST', 'DELETE'):
        return method_error(['POST', 'DELETE'])
    if request.method == 'POST' and not SKU.objects.filter(id=sku_id, is_launched=True).exists():
        return JsonResponse({'code': 404, 'error': '商品不存在或已下架'}, status=404)
    with transaction.atomic():
        UserProfile.objects.select_for_update().get(pk=request.user_profile.pk)
        own = BrowsingHistory.objects.filter(user=request.user_profile)
        if request.method == 'DELETE':
            own.filter(sku_id=sku_id).delete()
        else:
            BrowsingHistory.objects.update_or_create(
                user=request.user_profile, sku_id=sku_id,
                defaults={'viewed_time': timezone.now()},
            )
            stale = list(own.values_list('pk', flat=True)[HISTORY_LIMIT:])
            if stale:
                own.filter(pk__in=stale).delete()
    return JsonResponse({'code': 200, 'data': {}})
