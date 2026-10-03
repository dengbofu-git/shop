from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.db import transaction
from users.decorators import login_required, role_required
from orders.models import OrderInfo
from goods.models import SPU, SKU
from inventory.models import Inventory, Warehouse
from inventory.services import InventoryService
from .models import SupplierSettlement
from .analytics import build_supplier_analytics
import json


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('supplier'), name='dispatch')
class SupplierAnalyticsView(View):
    """供应商数据中心（基于订单库聚合）"""

    def get(self, request):
        user = request.user_profile
        period = request.GET.get('period') or 'year'
        data = build_supplier_analytics(user, period=period)
        return JsonResponse({'code': 200, 'data': data})


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('supplier'), name='dispatch')
class SupplierOrderListView(View):
    """供应商订单列表"""
    
    def get(self, request):
        user = request.user_profile
        status = request.GET.get('status')
        limit = request.GET.get('limit')
        
        # 获取供应商的商品SPU
        spus = SPU.objects.filter(merchant=user)
        skus = SKU.objects.filter(spu__in=spus)
        
        # 获取包含这些SKU的订单
        orders = OrderInfo.objects.filter(
            ordergoods__sku__in=skus
        ).distinct().order_by('-created_time')
        
        if status:
            if status.isdigit():
                orders = orders.filter(status=int(status))
            elif status == 'unshipped':
                orders = orders.filter(status=2)
            elif status == 'unpaid':
                orders = orders.filter(status=1)
            else:
                orders = orders.filter(status=status)
        if limit and str(limit).isdigit():
            orders = orders[: int(limit)]
        
        data = []
        for order in orders:
            order_goods = order.ordergoods_set.filter(sku__in=skus)
            total_amount = sum([og.count * og.price for og in order_goods])
            
            data.append({
                'order_id': order.order_id,
                'order_type': order.order_type,
                'status': order.status,
                'status_text': order.get_status_display_text(),
                'total_amount': float(total_amount),
                'total_count': sum([og.count for og in order_goods]),
                'receiver': order.receiver,
                'receiver_mobile': order.receiver_mobile,
                'address': order.address,
                'created_time': order.created_time.strftime('%Y-%m-%d %H:%M:%S'),
            })
        
        return JsonResponse({
            'code': 200,
            'data': data
        })


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('supplier'), name='dispatch')
class SupplierOrderShipView(View):
    """商家发货：将订单状态从 待发货(2) 改为 待收货(3)"""
    
    def post(self, request, order_id):
        user = request.user_profile
        spus = SPU.objects.filter(merchant=user)
        skus = SKU.objects.filter(spu__in=spus)
        
        try:
            order = OrderInfo.objects.get(order_id=order_id)
        except OrderInfo.DoesNotExist:
            return JsonResponse({'code': 404, 'error': '订单不存在'}, status=404)
        
        # 验证订单包含当前商家的商品
        order_skus = order.ordergoods_set.filter(sku__in=skus)
        if not order_skus.exists():
            return JsonResponse({'code': 403, 'error': '无权操作此订单'}, status=403)
        
        if order.status != 2:
            return JsonResponse({'code': 400, 'error': '当前状态不可发货，需为待发货'}, status=400)

        try:
            with transaction.atomic():
                for og in order_skus.select_for_update().select_related('sku'):
                    InventoryService.ship_deduct_sku(
                        og.sku_id, og.count, order_id=order.order_id
                    )
                order.status = 3
                order.save(update_fields=['status', 'updated_time'])
        except ValueError as e:
            return JsonResponse({'code': 400, 'error': str(e)}, status=400)
        except Exception:
            return JsonResponse({'code': 500, 'error': '发货失败，库存扣减异常'}, status=500)

        return JsonResponse({'code': 200, 'msg': '发货成功'})


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('supplier'), name='dispatch')
class SupplierOrderDeleteView(View):
    """供应商删除订单（仅支持待付款或已完成订单）"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            order_id = data.get('order_id')
            
            if not order_id:
                return JsonResponse({'code': 400, 'error': '缺少订单号'}, status=400)
            
            user = request.user_profile
            
            # 获取供应商的商品
            spus = SPU.objects.filter(merchant=user)
            skus = SKU.objects.filter(spu__in=spus)
            
            # 验证订单包含当前供应商的商品
            try:
                order = OrderInfo.objects.get(order_id=order_id)
            except OrderInfo.DoesNotExist:
                return JsonResponse({'code': 404, 'error': '订单不存在'}, status=404)
            
            order_skus = order.ordergoods_set.filter(sku__in=skus)
            if not order_skus.exists():
                return JsonResponse({'code': 403, 'error': '无权操作此订单'}, status=403)
            
            # 仅待付款(1)或已完成(4)订单可删除
            if order.status not in (1, 4):
                return JsonResponse({'code': 400, 'error': '仅待付款或已完成订单可删除'}, status=400)
            
            try:
                with transaction.atomic():
                    order.delete()
            except Exception as e:
                return JsonResponse({'code': 500, 'error': f'删除失败: {str(e)}'}, status=500)
            
            return JsonResponse({'code': 200, 'msg': '订单已删除'})
            
        except json.JSONDecodeError:
            return JsonResponse({'code': 400, 'error': '请求数据格式错误'}, status=400)
        except Exception as e:
            return JsonResponse({'code': 500, 'error': f'删除失败: {str(e)}'}, status=500)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('supplier'), name='dispatch')
class SupplierInventoryView(View):
    """供应商库存查看
    
    优先从 Inventory 表读取；若无记录则从 SKU.stock 展示（默认仓库）
    """
    
    def get(self, request):
        user = request.user_profile
        
        # 获取供应商的商品
        spus = SPU.objects.filter(merchant=user)
        skus = SKU.objects.filter(spu__in=spus)
        
        # 获取 Inventory 表中的库存（仅显示有数量的记录，已删除/清零的不展示）
        inventories = Inventory.objects.filter(sku__in=skus).select_related('sku', 'sku__spu', 'warehouse')
        sku_ids_with_inv = set()
        data = []
        for inv in inventories:
            sku_ids_with_inv.add(inv.sku_id)
            if inv.quantity > 0 or inv.available_quantity > 0:
                product_name = inv.sku.spu.name if inv.sku.spu else inv.sku.name
                data.append({
                    'sku_id': inv.sku.id,
                    'product_name': product_name,
                    'sku_name': inv.sku.name,
                    'warehouse': inv.warehouse.name if inv.warehouse else '默认',
                    'quantity': inv.quantity,
                    'available_quantity': inv.available_quantity,
                    'reserved_quantity': inv.reserved_quantity,
                })
        
        # 无 Inventory 记录的 SKU，使用 SKU.stock 展示（仅显示 stock > 0 的，已删除的不再展示）
        for sku in skus.select_related('spu'):
            if sku.id not in sku_ids_with_inv:
                stock = int(sku.stock) if sku.stock is not None else 0
                if stock > 0:
                    product_name = sku.spu.name if sku.spu else sku.name
                    data.append({
                        'sku_id': sku.id,
                        'product_name': product_name,
                        'sku_name': sku.name,
                        'warehouse': '默认',
                        'quantity': stock,
                        'available_quantity': stock,
                        'reserved_quantity': 0,
                    })
        
        return JsonResponse({
            'code': 200,
            'data': data
        })


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('supplier'), name='dispatch')
class SupplierInventoryUpdateView(View):
    """供应商库存更新"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            sku_id = data.get('sku_id')
            warehouse_name = data.get('warehouse', '默认')
            quantity = data.get('quantity')
            
            if not sku_id or quantity is None:
                return JsonResponse({'code': 400, 'error': '缺少必要参数'}, status=400)
            
            try:
                quantity = int(quantity)
                if quantity < 0:
                    return JsonResponse({'code': 400, 'error': '库存数量不能为负数'}, status=400)
            except (ValueError, TypeError):
                return JsonResponse({'code': 400, 'error': '库存数量格式错误'}, status=400)
            
            user = request.user_profile
            
            # 验证SKU属于当前供应商
            spus = SPU.objects.filter(merchant=user)
            skus = SKU.objects.filter(spu__in=spus, id=sku_id)
            if not skus.exists():
                return JsonResponse({'code': 403, 'error': '无权操作此商品'}, status=403)
            
            sku = skus.first()
            
            # 处理默认仓库的情况
            if warehouse_name == '默认':
                # 更新SKU的stock字段
                sku.stock = quantity
                sku.save(update_fields=['stock', 'updated_time'])
                
                # 获取或创建默认仓库，确保 Inventory 与 sku.stock 同步
                default_warehouse, _ = Warehouse.objects.get_or_create(
                    code='DEFAULT',
                    defaults={'name': '默认', 'address': '默认仓库', 'is_active': True}
                )
                if default_warehouse:
                    inv, created = Inventory.objects.get_or_create(
                        sku=sku,
                        warehouse=default_warehouse,
                        defaults={'quantity': quantity, 'available_quantity': quantity}
                    )
                    if not created:
                        inv.quantity = quantity
                        inv.available_quantity = quantity
                        inv.save(update_fields=['quantity', 'available_quantity', 'updated_time'])
                
                return JsonResponse({'code': 200, 'msg': '更新成功'})
            else:
                # 查找或创建仓库
                warehouse = Warehouse.objects.filter(name=warehouse_name).first()
                if not warehouse:
                    return JsonResponse({'code': 404, 'error': '仓库不存在'}, status=404)
                
                # 更新或创建Inventory记录
                inv, created = Inventory.objects.get_or_create(
                    sku=sku,
                    warehouse=warehouse,
                    defaults={'quantity': quantity, 'available_quantity': quantity}
                )
                if not created:
                    inv.quantity = quantity
                    inv.available_quantity = quantity
                    inv.save(update_fields=['quantity', 'available_quantity', 'updated_time'])
                
                return JsonResponse({'code': 200, 'msg': '更新成功'})
                
        except json.JSONDecodeError:
            return JsonResponse({'code': 400, 'error': '请求数据格式错误'}, status=400)
        except Exception as e:
            return JsonResponse({'code': 500, 'error': f'更新失败: {str(e)}'}, status=500)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('supplier'), name='dispatch')
class SupplierInventoryDeleteView(View):
    """供应商库存删除"""
    
    def post(self, request):
        try:
            data = json.loads(request.body)
            sku_id = data.get('sku_id')
            warehouse_name = data.get('warehouse', '默认')
            
            if not sku_id:
                return JsonResponse({'code': 400, 'error': '缺少必要参数'}, status=400)
            
            user = request.user_profile
            
            # 验证SKU属于当前供应商
            spus = SPU.objects.filter(merchant=user)
            skus = SKU.objects.filter(spu__in=spus, id=sku_id)
            if not skus.exists():
                return JsonResponse({'code': 403, 'error': '无权操作此商品'}, status=403)
            
            sku = skus.first()
            
            # 处理默认仓库的情况
            if warehouse_name == '默认':
                # 将SKU的stock设为0
                sku.stock = 0
                sku.save(update_fields=['stock', 'updated_time'])
                
                # 删除Inventory记录（如果存在）
                default_warehouse = Warehouse.objects.filter(code='DEFAULT').first()
                if default_warehouse:
                    Inventory.objects.filter(sku=sku, warehouse=default_warehouse).delete()
                
                return JsonResponse({'code': 200, 'msg': '删除成功'})
            else:
                # 查找仓库
                warehouse = Warehouse.objects.filter(name=warehouse_name).first()
                if not warehouse:
                    return JsonResponse({'code': 404, 'error': '仓库不存在'}, status=404)
                
                # 删除Inventory记录
                deleted_count = Inventory.objects.filter(sku=sku, warehouse=warehouse).delete()[0]
                if deleted_count > 0:
                    return JsonResponse({'code': 200, 'msg': '删除成功'})
                else:
                    return JsonResponse({'code': 404, 'error': '库存记录不存在'}, status=404)
                
        except json.JSONDecodeError:
            return JsonResponse({'code': 400, 'error': '请求数据格式错误'}, status=400)
        except Exception as e:
            return JsonResponse({'code': 500, 'error': f'删除失败: {str(e)}'}, status=500)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('supplier'), name='dispatch')
class SupplierSettlementView(View):
    """供应商结算跟踪"""
    
    def get(self, request):
        user = request.user_profile
        settlements = SupplierSettlement.objects.filter(supplier=user)
        
        data = []
        for settlement in settlements.select_related('order_info'):
            data.append({
                'order_id': settlement.order_info.order_id if settlement.order_info else '-',
                'amount': float(settlement.amount),
                'status': settlement.status,
                'status_text': settlement.get_status_display(),
                'settlement_time': settlement.settlement_time.strftime('%Y-%m-%d %H:%M:%S') if settlement.settlement_time else '-',
                'created_time': settlement.created_time.strftime('%Y-%m-%d %H:%M:%S') if settlement.created_time else '-',
            })
        
        return JsonResponse({
            'code': 200,
            'data': data
        })
