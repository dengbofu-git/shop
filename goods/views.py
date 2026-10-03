import base64
import mimetypes
from pathlib import Path

from django.http import HttpResponse, JsonResponse
from .models import Catalog
from .models import SKU, SPU, SKUImage
from django.db.models import F
from django.conf import settings
import json
from django.core import paginator


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
        'image': sku.default_image_url.name if sku.default_image_url else None,
        'image_text': spu_name or sku_name or caption or '商品图',
    }


def carousel(request):
    """
    首页/买家端轮播：从有库存的可售商品中选取，展示图片和简单介绍。
    GET: stable=1 不随机，按 id 降序；limit=N 条（默认 8）
    """
    import random
    skus = list(SKU.objects.filter(is_launched=True).select_related('spu')[:200])
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
        img_path = sku.default_image_url.name if sku.default_image_url else None
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
        'base_url': settings.DADASHOP_MEDIA
    })


def recommended_products(request):
    """推荐商品列表（公开API），有可用库存的推荐 SKU（与库存服务一致）。"""
    qs = SKU.objects.filter(
        is_recommended=True, is_launched=True
    ).select_related('spu').order_by('-updated_time', '-id')[:80]
    data = []
    for sku in qs:
        if _get_available_stock(sku) <= 0:
            continue
        spu = sku.spu
        catname = (spu.catalog.name if (spu and spu.catalog_id) else '') or ''
        row = _sku_public_dict(sku)
        row.update({
            'catalog_name': catname,
            'image_url': request.build_absolute_uri(f'/v1/goods/sku/{sku.id}/image'),
            'link': f'product_details.html?skuid={sku.id}',
        })
        data.append(row)
        if len(data) >= 20:
            break
    return JsonResponse({
        'code': 200,
        'data': data,
        'base_url': settings.DADASHOP_MEDIA
    })


def index(request):
    """首页：返回全部可售商品（按分类分组），仅显示有库存的商品"""
    data = []
    categories = Catalog.objects.all()
    for category in categories:
        sku_qs = SKU.objects.filter(
            spu__in=category.spu_set.all(), is_launched=True, stock__gt=0
        ).select_related('spu')
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
        "base_url": settings.DADASHOP_MEDIA,
    }
    return JsonResponse(context)


def catalogs(request, id):
    page = request.GET.get('page', 1)
    goods = Catalog.objects.get(id=id)
    sku_qs = SKU.objects.filter(
        spu__in=goods.spu_set.all(), is_launched=True, stock__gt=0
    ).select_related('spu').order_by('-id')
    data = [_sku_public_dict(sku) for sku in sku_qs]
    paginator_object = paginator.Paginator(data, 12)
    page_object = paginator_object.get_page(page)
    context = {
        'code': 200,
        'data': list(page_object),
        'paginator': {
            'pagesize': 12,
            'total': sku_qs.count()
        },
        'base_url': settings.DADASHOP_MEDIA
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
    """
    查找当前 SKU 对应的图片文件路径。
    优先当前 SKU，其次同 SPU 其他 SKU；跳过空文件。
    """
    def _valid_file(p):
        try:
            if not p:
                return False
            pp = Path(p) if not isinstance(p, Path) else p
            return pp.exists() and pp.is_file() and pp.stat().st_size > 0
        except (OSError, ValueError, TypeError):
            return False

    media_root = Path(settings.MEDIA_ROOT)
    sku_id = sku.id

    # 1. 当前 SKU：数据库路径
    image_field = _get_sku_image_field(sku)
    if image_field and getattr(image_field, 'name', None):
        for base_path in [
            Path(image_field.path) if hasattr(image_field, 'path') else None,
            media_root / image_field.name.replace('\\', '/'),
        ]:
            if _valid_file(base_path):
                return base_path

    # 2. 当前 SKU：sku/{sku_id}/ 下首张图
    sku_dir = media_root / 'sku' / str(sku_id)
    if sku_dir.exists():
        for ext in ('*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp'):
            for f in sku_dir.glob(ext):
                if _valid_file(f):
                    return f

    # 3. 当前 SKU：sku/{sku_id}.jpg 等
    for ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
        old_path = media_root / 'sku' / f'{sku_id}.{ext}'
        if _valid_file(old_path):
            return old_path

    # 4. 同 SPU 下其他 SKU 的图片（当前 SKU 无图时回退）
    for other in SKU.objects.filter(spu=sku.spu).exclude(id=sku.id):
        o_field = _get_sku_image_field(other)
        if o_field and getattr(o_field, 'name', None):
            for bp in [Path(o_field.path) if hasattr(o_field, 'path') else None,
                       media_root / o_field.name.replace('\\', '/')]:
                if _valid_file(bp):
                    return bp
        o_dir = media_root / 'sku' / str(other.id)
        if o_dir.exists():
            for ext in ('*.jpg', '*.jpeg', '*.png', '*.gif', '*.webp'):
                for f in o_dir.glob(ext):
                    if _valid_file(f):
                        return f
        for ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            op = media_root / 'sku' / f'{other.id}.{ext}'
            if _valid_file(op):
                return op

    return None


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
        sku = SKU.objects.get(id=sku_id)
    except SKU.DoesNotExist:
        return HttpResponse(status=404)
    file_path = _find_sku_image_file(sku)
    if not file_path:
        return _placeholder_image_response()
    content_type, _ = mimetypes.guess_type(str(file_path))
    if not content_type:
        content_type = 'image/jpeg'
    try:
        with open(file_path, 'rb') as f:
            return HttpResponse(f.read(), content_type=content_type)
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
    ).exclude(id=sku.id).values('name', 'price', skuid=F('id'), image=F('default_image_url'))[:8]
    rec_list = list(rec_skus)
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
        "base_url": settings.DADASHOP_MEDIA
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
