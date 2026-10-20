"""Merchant-owned draft/publish API and read-only public storefronts."""
import json
import uuid
import warnings
from functools import wraps
from io import BytesIO

from PIL import Image, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from users.decorators import get_user_from_request
from .models import StorePage
from .storefront import (active_merchants, default_content, product_row, public_products,
                         validate_content)


def error(message, status=400):
    return JsonResponse({'code': status, 'error': message}, status=status)


def active_merchant(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        user, denied = get_user_from_request(request)
        if denied is not None:
            return denied
        if not user.is_active or (not user.is_merchant() and not user.has_role('supplier')):
            return error('此功能仅向已激活的商家或供应商开放', 403)
        request.user_profile = user
        return view(request, *args, **kwargs)
    return wrapped


def owner_data(merchant, page):
    return {'merchant_id': merchant.pk, 'draft': page.draft if page else default_content(merchant),
            'revision': page.revision if page else 0,
            'is_published': bool(page and page.is_published),
            'has_unpublished_changes': bool(page and page.draft != page.published),
            'published_at': page.published_at.isoformat() if page and page.published_at else None,
            'public_url': f'/store.html?merchant_id={merchant.pk}'}


@never_cache
@require_http_methods(['GET', 'PUT', 'POST'])
@active_merchant
def manage(request):
    merchant = request.user_profile
    if request.method == 'GET':
        return JsonResponse({'code': 200, 'data': owner_data(
            merchant, StorePage.objects.filter(merchant=merchant).first())})
    try:
        payload = json.loads(request.body)
        allowed = {'revision', 'content'} if request.method == 'PUT' else {'revision', 'action'}
        if not isinstance(payload, dict) or set(payload) - allowed:
            return error('请求格式不正确')
        revision = payload.get('revision')
        if type(revision) is not int or revision < 0:
            return error('请重新加载页面后再保存')
        action = 'save' if request.method == 'PUT' else payload.get('action')
        if action not in ('save', 'publish', 'unpublish'):
            return error('不支持的店铺操作')
        # Save and publish are separate explicit operations, both with optimistic concurrency.
        with transaction.atomic():
            page, _ = StorePage.objects.get_or_create(merchant=merchant, defaults={'draft': default_content(merchant)})
            page = StorePage.objects.select_for_update().get(pk=page.pk)
            if revision != page.revision:
                return error('店铺已在其他页面更新，请重新加载并核对内容', 409)
            if action == 'save':
                page.draft = validate_content(payload.get('content'), merchant)
            elif action == 'publish':
                content = validate_content(page.draft, merchant)
                if not content['name']:
                    return error('发布前请填写店铺名称')
                page.published = content
                page.is_published = True
                page.published_at = timezone.now()
                # Existing account-facing shop information remains a single current identity.
                merchant.shop_name = content['name']
                merchant.shop_description = content['summary']
                merchant.save(update_fields=['shop_name', 'shop_description', 'updated_time'])
            else:
                page.is_published = False
            page.revision += 1
            page.save()
        return JsonResponse({'code': 200, 'data': owner_data(merchant, page)})
    except (json.JSONDecodeError, UnicodeDecodeError):
        return error('请提交有效的 JSON')
    except ValidationError as exc:
        return error(exc.messages[0])


@never_cache
@require_POST
@active_merchant
def upload(request):
    kind = request.POST.get('kind')
    image = request.FILES.get('image')
    if kind not in ('logo', 'banner') or image is None:
        return error('请选择 Logo 或横幅图片')
    if image.size > (4 if kind == 'logo' else 8) * 1024 * 1024:
        return error('Logo 最大 4MB，横幅最大 8MB')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(image) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or source.width * source.height > 20000000:
                    return error('请选择不超过 2000 万像素的 PNG、JPG 或 WebP 图片')
                source.load()
                # Re-encode a single raster frame; discard original metadata and active content.
                clean = source.convert('RGB')
                clean.thumbnail((800, 800) if kind == 'logo' else (2400, 1200))
                buffer = BytesIO()
                clean.save(buffer, format='WEBP', quality=88)
        name = f'store-pages/{request.user_profile.pk}/{kind}-{uuid.uuid4().hex}.webp'
        saved = default_storage.save(name, ContentFile(buffer.getvalue()))
        return JsonResponse({'code': 200, 'data': {'url': default_storage.url(saved)}})
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return error('图片无法读取，请选择有效的 PNG、JPG 或 WebP 图片')


@never_cache
@require_GET
def storefront(request, merchant_id):
    merchant = active_merchants().filter(pk=merchant_id).first()
    page = StorePage.objects.filter(merchant=merchant, is_published=True).first() if merchant else None
    if not page or not page.published:
        return error('店铺尚未发布或已下线，可返回平台继续浏览商品', 404)
    visible = public_products(merchant)
    selected = {sku.pk: sku for sku in visible.filter(pk__in=page.published.get('featured_ids', []))}
    featured = [product_row(selected[pk]) for pk in page.published.get('featured_ids', []) if pk in selected]
    content = {key: value for key, value in page.published.items() if key != 'featured_ids'}
    return JsonResponse({'code': 200, 'data': {'merchant_id': merchant_id, 'content': content,
                         'featured': featured, 'product_count': visible.count(),
                         'catalogs': list(visible.order_by('spu__catalog_id').values(
                             'spu__catalog_id', 'spu__catalog__name').distinct())}})


@never_cache
@require_GET
def products(request, merchant_id):
    merchant = active_merchants().filter(pk=merchant_id).first()
    if not merchant or not StorePage.objects.filter(merchant=merchant, is_published=True).exists():
        return error('店铺尚未发布或已下线', 404)
    query = public_products(merchant)
    keyword = request.GET.get('q', '').strip()[:100]
    if keyword:
        from django.db.models import Q
        query = query.filter(Q(name__icontains=keyword) | Q(spu__name__icontains=keyword))
    catalog = request.GET.get('catalog_id', '')
    if catalog:
        if not catalog.isdigit():
            return error('分类参数不正确')
        query = query.filter(spu__catalog_id=catalog)
    order = {'newest': '-id', 'sales': '-sales', 'price_asc': 'price', 'price_desc': '-price'}.get(
        request.GET.get('sort', 'newest'))
    if order is None:
        return error('排序参数不正确')
    paginator = Paginator(query.order_by(order, '-id') if order != '-id' else query.order_by('-id'), 10)
    page = paginator.get_page(request.GET.get('page', 1))
    return JsonResponse({'code': 200, 'data': [product_row(sku) for sku in page],
                         'pagination': {'page': page.number, 'pages': paginator.num_pages,
                                        'total': paginator.count, 'page_size': 10}})
