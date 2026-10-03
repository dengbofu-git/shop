from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from users.decorators import login_required, permission_required
from .services import InventoryService
from .models import Warehouse, Inventory
import json


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required('inventory_manage'), name='dispatch')
class InventoryListView(View):
    """库存列表"""
    
    def get(self, request):
        sku_id = request.GET.get('sku_id')
        warehouse_id = request.GET.get('warehouse_id')
        
        inventories = Inventory.objects.all()
        
        if sku_id:
            inventories = inventories.filter(sku_id=sku_id)
        if warehouse_id:
            inventories = inventories.filter(warehouse_id=warehouse_id)
        
        data = []
        for inv in inventories:
            data.append({
                'id': inv.id,
                'sku_id': inv.sku.id,
                'sku_name': inv.sku.name,
                'warehouse_id': inv.warehouse.id,
                'warehouse_name': inv.warehouse.name,
                'quantity': inv.quantity,
                'reserved_quantity': inv.reserved_quantity,
                'available_quantity': inv.available_quantity,
                'min_stock': inv.min_stock,
            })
        
        return JsonResponse({
            'code': 200,
            'data': data
        })


@method_decorator(login_required, name='dispatch')
@method_decorator(permission_required('inventory_manage'), name='dispatch')
class WarehouseListView(View):
    """仓库列表"""
    
    def get(self, request):
        warehouses = Warehouse.objects.filter(is_active=True)
        data = []
        for wh in warehouses:
            data.append({
                'id': wh.id,
                'name': wh.name,
                'code': wh.code,
                'address': wh.address,
                'province': wh.province,
                'city': wh.city,
            })
        
        return JsonResponse({
            'code': 200,
            'data': data
        })
