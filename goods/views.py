import base64
import mimetypes
from pathlib import Path

from django.http import HttpResponse, JsonResponse
from .models import Catalog
from .models import SKU, SPU, SKUImage
from django.db.models import F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.conf import settings
import json
from django.core import paginator
from .images import resolve_sku_image, sku_image_name


def _sku_public_dict(sku):
    """买家端列表/分类接口：返回 SPU 商品名与 SKU 规格字段。"""
    spu = sku.spu if hasattr(sku, 'spu') else None
    spu_name = (spu.name if spu else '') or ''
    sku_name = sku.name or ''
    caption = (sku.caption or '')[:120]
    return {
        'skuid': sku.id,
        'name': sku_name,
        'spu_name': spu_name,
        'product_name': spu_name,
        'caption': caption,
        'price': str(sku.price),
        'image': sku_image_name(sku) or None,
        'image_url': f'/v1/goods/sku/{sku.id}/image',
        'image_text': spu_name or sku_name or caption or '商品图',
    }


def carousel(request):
    """
    首页/买家端轮播：从有库存的可售商品中选取，展示图片和简单介绍。
    GET: stable=1 不随机，按 id 降序；limit=N 条（默认 8）
    """
    import random
    skus = list(SKU.objects.filter(is_launched=True).select_related('spu__catalog')[:200])
    skus_with_stock = []
    for sku in skus:
        if _get_available_stock(sku) > 0:
            skus_with_stock.append(sku)
    stable = request.GET.get('stable', '').lower() in ('1', 'true', 'yes')
    if stable:
        skus_with_stock.sort(key=lambda s: -s.id)
    else:
        random.shuffle(skus_with_stock)
    try:
        n = int(request.GET.get('limit', 8))
    except (TypeError, ValueError):
        n = 8
    n = max(1, min(n, 24))
    slides = skus_with_stock[:n]
    data = []
    for sku in slides:
        img_path = sku_image_name(sku) or None
        image_url = request.build_absolute_uri(f'/v1/goods/sku/{sku.id}/image') if sku.id else None
        intro = (sku.caption or sku.name or sku.spu.name or '')[:80]
        data.append({
            'skuid': sku.id,
            'title': sku.spu.name or sku.name,
            'intro': intro,
            'image': img_path,
            'image_url': image_url,
            'link_url': f'product_details.html?skuid={sku.id}',
            'price': str(sku.price),
        })
    return JsonResponse({
        'code': 200,
        'data': data,
        'base_url': settings.TEA_SAAS_MEDIA
    })


def recommended_products(request):
    """全平台已上架且有库存的 SKU，按销量优先；不要求人工推荐标记。"""
    # Preserve this catalog's max(SKU.stock, summed ledger availability) eligibility.
    # Filter before limiting so sold-out top sellers cannot exhaust a candidate window.
    qs = SKU.objects.filter(is_launched=True).select_related('spu__catalog').annotate(
        ledger_available=Coalesce(Sum('inventory__available_quantity'), Value(0)),
    ).filter(Q(stock__gt=0) | Q(ledger_available__gt=0)).order_by(
        '-sales', '-updated_time', '-id'
    )[:20]
    data = []
    for sku in qs:
        spu = sku.spu
        catname = (spu.catalog.name if (spu and spu.catalog_id) else '') or ''
        row = _sku_public_dict(sku)
        row.update({
            'catalog_name': catname,
            'image_url': request.build_absolute_uri(f'/v1/goods/sku/{sku.id}/image'),
            'link': f'product_details.html?skuid={sku.id}',
        })
        data.append(row)
    return JsonResponse({
        'code': 200,
        'data': data,
        'base_url': settings.TEA_SAAS_MEDIA
    })


def index(request):
    """首页：返回全部可售商品（按分类分组），仅显示有库存的商品"""
    data = []
    categories = Catalog.objects.all()
    for category in categories:
        sku_qs = SKU.objects.filter(
            spu__in=category.spu_set.all(), is_launched=True, stock__gt=0
        ).select_related('spu__catalog')
        sku_list = [_sku_public_dict(sku) for sku in sku_qs]
        if sku_list:  # 只返回有商品的分类
            data.append({
                'catalog_id': category.id,
                'catalog_name': category.name,
                'sku': sku_list,
            })
    context = {
        'code': 200,
        'data': data,
        "base_url": settings.TEA_SAAS_MEDIA,
    }
    return JsonResponse(context)


def catalogs(request, id):
    page = request.GET.get('page', 1)
    try:
        page_size = int(request.GET.get('page_size', 12))
    except (TypeError, ValueError):
        page_size = 12
    if not 1 <= page_size <= 100:
        page_size = 12
    goods = Catalog.objects.get(id=id)
    sku_qs = SKU.objects.filter(
        spu__in=goods.spu_set.all(), is_launched=True, stock__gt=0
    ).select_related('spu__catalog').order_by('-id')
    data = [_sku_public_dict(sku) for sku in sku_qs]
    paginator_object = paginator.Paginator(data, page_size)
    page_object = paginator_object.get_page(page)
    context = {
        'code': 200,
        'data': list(page_object),
        'paginator': {
            'pagesize': page_size,
            'total': sku_qs.count()
        },
        'base_url': settings.TEA_SAAS_MEDIA
    }
    return JsonResponse(context)


def _get_media_image_url(sku, request):
    """获取当前 SKU 图片的 media 直链 URL"""
    file_path = _find_sku_image_file(sku)
    if not file_path:
        return None
    try:
        rel_path = file_path.relative_to(Path(settings.MEDIA_ROOT))
        path_str = str(rel_path).replace('\\', '/')
        base = (settings.MEDIA_URL or '/media/').rstrip('/')
        return request.build_absolute_uri(f'{base}/{path_str}')
    except ValueError:
        return None


def _get_sku_image_base64(sku):
    """
    从当前 SKU 对应路径读取图片，返回 base64 数据 URI。
    确保图片与商品 SKU 一一对应。
    """
    file_path = _find_sku_image_file(sku)
    if not file_path:
        return None
    try:
        content_type, _ = mimetypes.guess_type(str(file_path))
        if not content_type:
            content_type = 'image/jpeg'
        with open(file_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        return f'data:{content_type};base64,{b64}'
    except (OSError, ValueError):
        return None


def _get_sku_image_field(sku):
    """获取当前 SKU 的图片字段：优先 default_image_url，否则 SKUImage（仅当前 SKU）"""
    image_field = sku.default_image_url
    if not image_field:
        first_img = SKUImage.objects.filter(sku=sku).first()
        if first_img:
            image_field = first_img.image
    return image_field


def _get_sku_image_path_for_api(sku):
    """返回当前 SKU 图片的 media 相对路径，供 API 使用"""
    file_path = _find_sku_image_file(sku)
    if not file_path:
        return sku.default_image_url.name if sku.default_image_url else None
    try:
        rel = file_path.relative_to(Path(settings.MEDIA_ROOT))
        return str(rel).replace('\\', '/')
    except ValueError:
        return sku.default_image_url.name if sku.default_image_url else None


def _find_sku_image_file(sku):
    """兼容现有调用：真实商品图片优先，其次使用已登记的茶类虚拟图。"""
    selection = resolve_sku_image(sku)
    return selection.path if selection else None


def _placeholder_image_response():
    """
    SKU 无本地图片文件时返回占位图，避免 /v1/goods/sku/<id>/image 返回 404
    （买家工作台「精选商品」等页面用该 URL 作为 <img src>）。
    """
    candidates = [
        Path(settings.BASE_DIR) / 'client' / 'static' / 'images' / 'cart' / 'product_normal.png',
        Path(settings.BASE_DIR) / 'client' / 'static' / 'images' / 'goods' / '7.jpg',
    ]
    for p in candidates:
        try:
            if p.is_file() and p.stat().st_size > 0:
                content_type, _ = mimetypes.guess_type(str(p))
                if not content_type:
                    content_type = 'application/octet-stream'
                with open(p, 'rb') as fh:
                    return HttpResponse(fh.read(), content_type=content_type)
        except OSError:
            continue
    # 1×1 透明 PNG（不依赖静态目录是否存在）
    body = base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=='
    )
    return HttpResponse(body, content_type='image/png')


def sku_image(request, sku_id):
    """直接返回当前 SKU 对应的图片文件"""
    try:
        sku = SKU.objects.select_related('spu__catalog').get(id=sku_id)
    except SKU.DoesNotExist:
        return HttpResponse(status=404)
    selection = resolve_sku_image(sku)
    if not selection:
        return _placeholder_image_response()
    file_path = selection.path
    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = 'image/jpeg'
    try:
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type=content_type)
            response['X-Image-Source'] = 'catalog-virtual' if selection.is_virtual else 'product-upload'
            return response
    except OSError:
        return HttpResponse(status=404)


def _get_available_stock(sku):
    """
    获取 SKU 可用库存。
    取 Inventory 多仓库汇总 与 sku.stock 的较大值，避免两处数据不同步时显示错误。
    """
    sku_stock = int(sku.stock) if sku.stock is not None else 0
    try:
        from inventory.models import Inventory
        from inventory.services import InventoryService
        inv_total = InventoryService.get_available_quantity(sku.id)
        return max(inv_total, sku_stock)
    except Exception:
        pass
    return sku_stock


def detail(request, id):
    try:
        sku = SKU.objects.get(id=id)
    except SKU.DoesNotExist:
        context = {
            "code": 404,
            "error": f"商品ID {id} 不存在"
        }
        return JsonResponse(context)
    except Exception as e:
        context = {
            "code": 500,
            "error": f"服务器错误: {str(e)}"
        }
        return JsonResponse(context)

    # 真实规格参数：商品名称用 SPU 名称，规格用 SKU 名称
    spu_name = sku.spu.name
    spec_list = [
        {"name": "商品名称", "value": spu_name},
        {"name": "规格", "value": sku.name},
        {"name": "所属分类", "value": sku.spu.catalog.name},
    ]
    if sku.spu.brand:
        spec_list.append({"name": "品牌", "value": sku.spu.brand.name})
    for sv in sku.skuspecvalue_set.select_related('spu_spec').all():
        spec_list.append({"name": sv.spu_spec.name, "value": sv.name})
    spec_dict = {item["name"]: item["value"] for item in spec_list}

    # 商品介绍：使用 caption，无则用 name
    product_intro = sku.caption or sku.name or ""

    # 为你推荐：同分类下其他可售商品（排除当前，仅显示有库存）
    from django.db.models import F
    rec_skus = SKU.objects.filter(
        spu__catalog=sku.spu.catalog,
        is_launched=True,
        stock__gt=0
    ).exclude(id=sku.id).select_related('spu__catalog')[:8]
    rec_list = [_sku_public_dict(item) for item in rec_skus]
    for r in rec_list:
        r['image_text'] = r.get('name') or '商品图'

    spu_sale_attrs = list(sku.spu.spusaleattr_set.all())
    selected_val_ids = []
    for attr in spu_sale_attrs:
        sel = sku.sale_attr_value.filter(spu_sale_attr=attr).first()
        all_vals = list(attr.saleattrvalue_set.all())
        selected_val_ids.append(sel.id if sel else (all_vals[0].id if all_vals else 0))

    context = {
        "code": 200,
        "data": {
            "catalog_id": sku.spu.catalog_id,
            "is_launched": sku.is_launched,
            "catalog_name": sku.spu.catalog.name,
            "spu_name": spu_name,
            "product_name": spu_name,
            "name": sku.name,
            "caption": sku.caption,
            "price": str(sku.price),
            "stock": _get_available_stock(sku),
            "image": _get_sku_image_path_for_api(sku),
            "image_base64": _get_sku_image_base64(sku),
            "image_url": request.build_absolute_uri(f'/v1/goods/sku/{id}/image'),
            "media_image_url": _get_media_image_url(sku, request),
            "image_text": spu_name or sku.name or sku.caption or "商品图",
            "spu": sku.spu_id,
            "detail_image": _get_sku_image_path_for_api(sku),
            "spec": spec_dict,
            "spec_list": spec_list,
            "product_intro": product_intro,
            "recommended": rec_list,
            "sku_sale_attr_id": [item.id for item in spu_sale_attrs],
            "sku_sale_attr_names": [item.name for item in spu_sale_attrs],
            "sku_sale_attr_val_id": selected_val_ids,
            "sku_sale_attr_val_names": [temp.name for item in spu_sale_attrs for temp in item.saleattrvalue_set.all()],
            "sku_all_sale_attr_vals_id": {item.id: [temp.id for temp in item.saleattrvalue_set.all()] for item in spu_sale_attrs},
            "sku_all_sale_attr_vals_name": {item.id: [temp.name for temp in item.saleattrvalue_set.all()] for item in spu_sale_attrs},
        },
        "base_url": settings.TEA_SAAS_MEDIA
    }
    return JsonResponse(context)


def sku(request):
    data = json.loads(request.body)
    spu_id = data.get('spuid')
    spu = SPU.objects.get(id=spu_id)
    sku_objects = spu.sku_set.all()
    data.pop('spuid')
    ##每次筛选一种属性，直到所有属性都满足。
    for key,val in data.items():
        sku_subjects = sku_objects.filter(sale_attr_value=val)
    context = {
        'code': 200,
        'data': sku_subjects[0].id,
    }
    return JsonResponse(context)
