"""
店家商品管理视图
只有店家可以访问
"""
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction
from users.decorators import merchant_required
from .models import SPU, SKU, Catalog, Brand, SPUSaleAttr, SaleAttrValue
from django.conf import settings
import json


TEA_CATEGORIES = ('红茶', '绿茶', '乌龙茶', '普洱茶', '白茶', '黄茶', '花茶')


@merchant_required
@require_http_methods(["GET"])
def brands_and_catalogs(request):
    """获取品牌和分类列表（供创建SPU时选择）"""
    try:
        brands = [{'id': b.id, 'name': b.name} for b in Brand.objects.all()]
        existing_catalogs = {
            catalog.name: catalog.id
            for catalog in Catalog.objects.filter(name__in=TEA_CATEGORIES)
        }
        catalogs = [
            {'id': existing_catalogs.get(name), 'name': name}
            for name in TEA_CATEGORIES
        ]
        return JsonResponse({
            'code': 200,
            'data': {'brands': brands, 'catalogs': catalogs}
        })
    except Exception as e:
        return JsonResponse({'code': 500, 'error': str(e)})


@merchant_required
@require_http_methods(["POST"])
def create_spu(request):
    """
    创建商品主记录。商家界面使用商品名称，品牌为可选项。
    """
    try:
        data = json.loads(request.body)
        merchant = request.user_profile
        
        name = (data.get('name') or '').strip()
        catalog_name = (data.get('catalog_name') or data.get('catalog') or '').strip()
        
        if not name:
            return JsonResponse({'code': 400, 'error': '请填写商品名称'})
        if catalog_name not in TEA_CATEGORIES:
            return JsonResponse({'code': 400, 'error': '请选择茶叶品种'})
        
        # 分类：存在则用，不存在则创建
        catalog, _ = Catalog.objects.get_or_create(name=catalog_name)
        
        # 品牌：可选，不再强制
        brand = None
        brand_name = (data.get('brand_name') or data.get('brand') or '').strip()
        if brand_name:
            brand, _ = Brand.objects.get_or_create(
                name=brand_name,
                defaults={'first_letter': (brand_name[0] if brand_name else 'A').upper()[:1]}
            )
        
        # 创建SPU
        spu = SPU.objects.create(
            name=name,
            brand=brand,
            catalog=catalog,
            merchant=merchant,
            sales=0,
            comments=0
        )
        
        return JsonResponse({
            'code': 200,
            'msg': '商品创建成功',
            'data': {
                'spu_id': spu.id,
                'name': spu.name
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'code': 500,
            'error': f'创建失败: {str(e)}'
        })


@merchant_required
@require_http_methods(["POST"])
def create_sku(request):
    """
    创建商品销售记录。前端将商品名称同步为销售记录名称，商品介绍存入 caption。
    """
    try:
        data = json.loads(request.body)
        merchant = request.user_profile
        
        spu_id = data.get('spu_id')
        spu_name = (data.get('spu_name') or '').strip()
        
        if spu_id:
            try:
                spu = SPU.objects.get(id=int(spu_id), merchant=merchant)
            except (SPU.DoesNotExist, ValueError):
                return JsonResponse({'code': 404, 'error': '商品不存在或不属于当前店家'})
        elif spu_name:
            spu = SPU.objects.filter(name=spu_name, merchant=merchant).first()
            if not spu:
                return JsonResponse({'code': 404, 'error': f'未找到商品「{spu_name}」，请先添加该商品'})
        else:
            return JsonResponse({'code': 400, 'error': '请填写商品名称'})
        
        name = data.get('name')
        caption = data.get('caption', '')
        price = data.get('price')
        stock = data.get('stock', 0)
        
        if not name:
            return JsonResponse({'code': 400, 'error': '请填写商品名称'})
        if price is None or price == '':
            return JsonResponse({'code': 400, 'error': '请填写售价'})
        
        # 库存默认0
        try:
            stock_val = int(stock) if stock not in (None, '') else 0
        except (ValueError, TypeError):
            stock_val = 0
        
        # 创建SKU
        sku = SKU.objects.create(
            name=name,
            caption=caption or '',
            spu=spu,
            price=float(price),
            cost_price=float(data.get('cost_price', 0)),
            market_price=float(data.get('market_price', price)),
            stock=stock_val,
            sales=0,
            comments=0,
            is_launched=data.get('is_launched', True)
        )
        
        # 处理销售属性值（如果有）
        if 'sale_attr_values' in data:
            sale_attr_value_ids = data['sale_attr_values']
            sku.sale_attr_value.set(sale_attr_value_ids)
        
        return JsonResponse({
            'code': 200,
            'msg': '商品创建成功',
            'data': {
                'sku_id': sku.id,
                'name': sku.name,
                'price': str(sku.price),
                'stock': sku.stock
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'code': 500,
            'error': f'创建失败: {str(e)}'
        })


@merchant_required
@require_http_methods(["GET"])
def my_products(request):
    """
    获取店家的商品列表
    """
    try:
        merchant = request.user_profile
        
        # 获取SPU列表
        spus = SPU.objects.filter(merchant=merchant).select_related('brand', 'catalog')
        
        products = []
        for spu in spus:
            # 获取该SPU下的所有SKU
            skus = SKU.objects.filter(spu=spu)
            sku_list = []
            for sku in skus:
                sku_list.append({
                    'sku_id': sku.id,
                    'name': sku.name,
                    'caption': sku.caption or '',
                    'price': str(sku.price),
                    'stock': sku.stock,
                    'sales': sku.sales,
                    'is_launched': sku.is_launched,
                    'image': request.build_absolute_uri(f'/v1/goods/sku/{sku.id}/image')
                })
            
            products.append({
                'spu_id': spu.id,
                'name': spu.name,
                'brand': spu.brand.name if spu.brand else '',
                'catalog': spu.catalog.name,
                'sales': spu.sales,
                'comments': spu.comments,
                'skus': sku_list
            })
        
        return JsonResponse({
            'code': 200,
            'data': products
        })
        
    except Exception as e:
        return JsonResponse({
            'code': 500,
            'error': f'获取失败: {str(e)}'
        })


@merchant_required
def spu_detail(request, spu_id):
    """SPU 详情操作：PUT 修改，DELETE 删除"""
    if request.method == 'PUT':
        return _update_spu(request, spu_id)
    elif request.method == 'DELETE':
        return _delete_spu(request, spu_id)
    return JsonResponse({'code': 405, 'error': '方法不允许'}, status=405)


def _update_spu(request, spu_id):
    try:
        merchant = request.user_profile
        data = json.loads(request.body)
        spu = SPU.objects.get(id=spu_id, merchant=merchant)
    except SPU.DoesNotExist:
        return JsonResponse({'code': 404, 'error': '商品不存在或无权操作'})
    except Exception as e:
        return JsonResponse({'code': 500, 'error': str(e)})
    name = data.get('name', '').strip()
    if name:
        spu.name = name
    brand_name = (data.get('brand_name') or data.get('brand') or '').strip()
    if brand_name:
        brand, _ = Brand.objects.get_or_create(name=brand_name, defaults={'first_letter': (brand_name[0] if brand_name else 'A').upper()[:1]})
        spu.brand = brand
    catalog_name = (data.get('catalog_name') or data.get('catalog') or '').strip()
    if catalog_name:
        if catalog_name not in TEA_CATEGORIES:
            return JsonResponse({'code': 400, 'error': '请选择茶叶品种'})
        catalog, _ = Catalog.objects.get_or_create(name=catalog_name)
        spu.catalog = catalog
    spu.save()
    return JsonResponse({'code': 200, 'msg': '修改成功', 'data': {'spu_id': spu.id, 'name': spu.name}})


def _delete_spu(request, spu_id):
    from django.db.models.deletion import ProtectedError
    try:
        merchant = request.user_profile
        spu = SPU.objects.get(id=spu_id, merchant=merchant)
        spu.delete()
        return JsonResponse({'code': 200, 'msg': '删除成功'})
    except ProtectedError:
        return JsonResponse({'code': 409, 'error': '商品已有交易或评价记录，请使用下架保留历史'}, status=409)
    except SPU.DoesNotExist:
        return JsonResponse({'code': 404, 'error': '商品不存在或无权操作'})
    except Exception as e:
        return JsonResponse({'code': 500, 'error': str(e)})


@merchant_required
def sku_detail(request, sku_id):
    """SKU 详情操作：PUT 修改，DELETE 删除"""
    if request.method == 'PUT':
        return _update_sku(request, sku_id)
    elif request.method == 'DELETE':
        return _delete_sku(request, sku_id)
    return JsonResponse({'code': 405, 'error': '方法不允许'}, status=405)


@transaction.atomic
def _update_sku(request, sku_id):
    try:
        merchant = request.user_profile
        data = json.loads(request.body)
        sku = SKU.objects.select_for_update().select_related('spu').get(id=sku_id)
        if sku.spu.merchant != merchant:
            return JsonResponse({'code': 403, 'error': '无权操作'})
    except SKU.DoesNotExist:
        return JsonResponse({'code': 404, 'error': '商品不存在'})
    except Exception as e:
        return JsonResponse({'code': 500, 'error': str(e)})
    if 'name' in data and data['name']:
        sku.name = data['name']
    if 'caption' in data:
        sku.caption = data.get('caption', '')
    if 'is_launched' in data:
        sku.is_launched = data['is_launched']
    if 'stock' in data:
        from inventory.services import InventoryService
        try:sku.stock = InventoryService.adjust_stock(sku.pk,int(data['stock']))
        except (ValueError,TypeError):return JsonResponse({'code':409,'error':'库存调整失败：不能低于已预留数量，多仓库存请按仓库调整'},status=409)
    if 'price' in data:
        sku.price = data['price']
    sku.save(update_fields=[k for k in ('name','caption','is_launched','price') if k in data]+['updated_time'])
    return JsonResponse({'code': 200, 'msg': '修改成功', 'data': {'sku_id': sku.id, 'name': sku.name, 'price': str(sku.price), 'stock': sku.stock}})


def _delete_sku(request, sku_id):
    from django.db.models.deletion import ProtectedError
    try:
        merchant = request.user_profile
        sku = SKU.objects.select_related('spu').get(id=sku_id)
        if sku.spu.merchant != merchant:
            return JsonResponse({'code': 403, 'error': '无权操作'})
        sku.delete()
        return JsonResponse({'code': 200, 'msg': '删除成功'})
    except ProtectedError:
        return JsonResponse({'code': 409, 'error': '商品已有交易或评价记录，请使用下架保留历史'}, status=409)
    except SKU.DoesNotExist:
        return JsonResponse({'code': 404, 'error': '商品不存在'})
    except Exception as e:
        return JsonResponse({'code': 500, 'error': str(e)})


@merchant_required
@require_http_methods(["POST"])
def upload_sku_image(request, sku_id):
    """
    上传SKU商品图片
    接受 multipart/form-data，字段名 image
    """
    try:
        merchant = request.user_profile
        sku = SKU.objects.select_related('spu').get(id=sku_id)
        if sku.spu.merchant != merchant:
            return JsonResponse({'code': 403, 'error': '无权操作'})
    except SKU.DoesNotExist:
        return JsonResponse({'code': 404, 'error': '商品不存在'})
    image_file = request.FILES.get('image')
    if not image_file:
        return JsonResponse({'code': 400, 'error': '请选择商品图片'})
    sku.default_image_url = image_file
    sku.save(update_fields=['default_image_url','updated_time'])
    return JsonResponse({
        'code': 200,
        'msg': '图片上传成功',
        'data': {'image_url': str(sku.default_image_url)}
    })


@merchant_required
@require_http_methods(["PUT"])
@transaction.atomic
def update_sku_status(request, sku_id):
    """
    更新SKU上架状态
    """
    try:
        merchant = request.user_profile
        data = json.loads(request.body)
        
        # 获取SKU并验证所有权
        try:
            sku = SKU.objects.select_for_update().select_related('spu').get(id=sku_id)
            if sku.spu.merchant != merchant:
                return JsonResponse({
                    'code': 403,
                    'error': '无权操作此商品'
                })
        except SKU.DoesNotExist:
            return JsonResponse({
                'code': 404,
                'error': '商品不存在'
            })
        
        # 更新字段（支持 name、caption、price、stock、is_launched）
        if 'name' in data and data['name']:
            sku.name = data['name']
        if 'caption' in data:
            sku.caption = data.get('caption', '')
        if 'is_launched' in data:
            sku.is_launched = data['is_launched']
        if 'stock' in data:
            from inventory.services import InventoryService
            try:sku.stock = InventoryService.adjust_stock(sku.pk,int(data['stock']))
            except (ValueError,TypeError):return JsonResponse({'code':409,'error':'库存调整失败，请检查已预留库存及仓库'},status=409)
        if 'price' in data:
            sku.price = data['price']
        
        sku.save(update_fields=[k for k in ('name','caption','is_launched','price') if k in data]+['updated_time'])
        
        return JsonResponse({
            'code': 200,
            'msg': '更新成功',
            'data': {
                'sku_id': sku.id,
                'is_launched': sku.is_launched,
                'stock': sku.stock,
                'price': str(sku.price)
            }
        })
        
    except Exception as e:
        transaction.set_rollback(True)
        return JsonResponse({
            'code': 500,
            'error': f'更新失败: {str(e)}'
        })
