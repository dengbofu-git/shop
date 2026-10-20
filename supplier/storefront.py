"""Storefront rules and explicit public projections, separate from account details."""
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db.models import Q

from goods.models import SKU
from users.models import UserProfile


TEXT_LIMITS = {'name': 50, 'summary': 200, 'welcome': 100, 'story': 5000}


def default_content(merchant):
    return {'name': merchant.shop_name or '', 'summary': merchant.shop_description or '',
            'welcome': '', 'story': '', 'logo_url': '', 'banner_url': '', 'featured_ids': []}


def validate_content(value, merchant):
    if not isinstance(value, dict):
        raise ValidationError('店铺内容格式不正确')
    allowed = set(TEXT_LIMITS) | {'logo_url', 'banner_url', 'featured_ids'}
    if set(value) - allowed:
        raise ValidationError('店铺内容包含不支持的字段')
    result = {}
    for key, limit in TEXT_LIMITS.items():
        text = value.get(key, '')
        if not isinstance(text, str) or len(text.strip()) > limit:
            raise ValidationError(f'{key} 内容过长或格式不正确')
        result[key] = text.strip()
    # Store only URLs created by this merchant's upload endpoint. Never accept HTML/SVG/remote URLs.
    prefix = f'{settings.MEDIA_URL.rstrip("/")}/store-pages/{merchant.pk}/'
    for key in ('logo_url', 'banner_url'):
        url = value.get(key, '')
        if not isinstance(url, str) or (url and (
                not url.startswith(prefix) or len(url) > 300 or '..' in url or
                '?' in url or '#' in url or '\\' in url or '%' in url or
                not url.lower().endswith(('.jpg', '.png', '.webp')))):
            raise ValidationError('请使用本店上传的 Logo 或横幅')
        result[key] = url
    ids = value.get('featured_ids', [])
    if not isinstance(ids, list) or len(ids) > 8 or any(type(i) is not int or i <= 0 for i in ids):
        raise ValidationError('最多选择 8 个推荐商品')
    if len(set(ids)) != len(ids):
        raise ValidationError('推荐商品不能重复')
    if SKU.objects.filter(pk__in=ids, spu__merchant=merchant).count() != len(ids):
        raise ValidationError('只能选择本店仍然存在的商品')
    result['featured_ids'] = ids
    return result


def active_merchants():
    return UserProfile.objects.filter(is_active=True).filter(
        Q(user_type='merchant') | Q(userrole__role__code='supplier')).distinct()


def public_merchant(spu):
    """No username, contact details, draft content or other private account fields."""
    merchant = getattr(spu, 'merchant', None) if spu else None
    if merchant is None:
        return None
    try:
        page = merchant.store_page
    except ObjectDoesNotExist:
        page = None
    available = bool(merchant.is_active and page and page.is_published and page.published and
                     (merchant.is_merchant() or merchant.has_role('supplier')))
    return {'id': merchant.pk, 'name': (page.published['name'] if available else
                                       merchant.shop_name or '商家店铺'),
            'url': f'/store.html?merchant_id={merchant.pk}' if available else None,
            'is_published': available}


def public_products(merchant):
    # Match the platform index eligibility without changing existing inventory semantics.
    return SKU.objects.filter(spu__merchant=merchant, is_launched=True, stock__gt=0).select_related(
        'spu__catalog', 'spu__merchant__store_page')


def product_row(sku):
    from goods.views import _sku_public_dict
    row = _sku_public_dict(sku)
    row.update({'catalog_id': sku.spu.catalog_id, 'catalog_name': sku.spu.catalog.name,
                'sales': sku.sales})
    return row
