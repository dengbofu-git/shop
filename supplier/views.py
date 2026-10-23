from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.db import transaction
from users.decorators import login_required, role_required
from orders.models import OrderInfo
from orders.lifecycle import can_delete, can_ship, merchant_ids, state_record, status_filter
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
        from .workbench import owned_items
        from orders.models import OrderGoods
        owned = OrderGoods.objects.filter(owned_items(user))
        orders = OrderInfo.objects.filter(pk__in=owned.values('order_info_id')).distinct().select_related('trialorder', 'presaleorder').order_by('-created_time')
        
        if status:
            value = {'unshipped': 2, 'unpaid': 1}.get(status)
            if status.isdigit() and int(status) in (0, 1, 2, 3, 4):
                value = int(status)
            if value is None:
                return JsonResponse({'code': 400, 'error': '订单状态筛选不正确'}, status=400)
            orders = orders.filter(status_filter(value))
        if limit and str(limit).isdigit():
            orders = orders[: int(limit)]
        
        data = []
        for order in orders:
            order_goods = order.ordergoods_set.filter(owned_items(user))
            total_amount = sum([og.count * og.price for og in order_goods])
            owned_only = merchant_ids(order) == {user.pk}
            
            data.append({
                'order_id': order.order_id,
                'order_type': order.order_type,
                'status': order.status,
                'status_text': order.get_status_display_text(),
                'can_ship': owned_only and can_ship(order),
                'can_delete': owned_only and can_delete(order),
                'requires_merchant_split': not owned_only,
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
        from orders.reservations import ship_order,ReservationError
        from orders.checkout_views import error_response
        try:
            ship_order(order_id,request.user_profile)
            return JsonResponse({'code':200,'msg':'发货成功'})
        except ReservationError as exc:return error_response(exc)
        except ValueError as exc:return JsonResponse({'code':409,'error':str(exc)},status=409)


@method_decorator(login_required, name='dispatch')
@method_decorator(role_required('supplier'), name='dispatch')
class SupplierOrderDeleteView(View):
    """Retained endpoint cancels an unpaid standard order without deleting history."""
    def post(self, request):
        from orders.reservations import close_order, ReservationError
        from orders.checkout_views import error_response
        from orders.lifecycle import require_single_merchant, OrderActionError
        user=request.user_profile
        if not user.is_active:return JsonResponse({'code':403,'error':'当前账号已停用'},status=403)
        try:
            data=json.loads(request.body)
            if not isinstance(data,dict) or not isinstance(data.get('order_id'),str) or not data['order_id']:
                raise ValueError()
            order=OrderInfo.objects.get(pk=data['order_id'])
            require_single_merchant(order,user)
            if not can_delete(order):return JsonResponse({'code':409,'error':'当前订单须保留履约和交易记录，不能删除'},status=409)
            close_order(order.pk,merchant_id=user.pk)
            return JsonResponse({'code':200,'msg':'订单已取消，库存已释放，记录保留'})
        except OrderInfo.DoesNotExist:return JsonResponse({'code':404,'error':'订单不存在'},status=404)
        except OrderActionError as exc:return JsonResponse({'code':exc.status,'error':str(exc)},status=exc.status)
        except ReservationError as exc:return error_response(exc)
        except (ValueError,TypeError,AttributeError):return JsonResponse({'code':400,'error':'请求数据格式错误'},status=400)


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
            
            try:
                InventoryService.adjust_stock(sku.pk,quantity,warehouse_name)
            except ValueError as exc:return JsonResponse({'code':409,'error':str(exc)},status=409)
            return JsonResponse({'code':200,'msg':'更新成功'})

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
            
            try:
                InventoryService.adjust_stock(sku.pk,0,warehouse_name)
            except ValueError as exc:return JsonResponse({'code':409,'error':str(exc)},status=409)
            return JsonResponse({'code':200,'msg':'库存已清零，账本保留'})

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
