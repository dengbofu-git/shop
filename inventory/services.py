"""
智能库存服务
"""
from django.db import transaction
from django.db.models import Sum, F
from .models import Warehouse, Inventory, InventoryLog
from goods.models import SKU


class InventoryService:
    """库存服务类"""
    
    @staticmethod
    def get_available_quantity(sku_id, warehouse_id=None):
        """获取可用库存数量"""
        if warehouse_id:
            inventory = Inventory.objects.filter(sku_id=sku_id, warehouse_id=warehouse_id).first()
            return inventory.available_quantity if inventory else 0
        else:
            # 获取所有仓库的可用库存总和
            total = Inventory.objects.filter(sku_id=sku_id).aggregate(
                total=Sum('available_quantity')
            )['total']
            return total or 0
    
    @staticmethod
    def reserve_inventory(sku_id, warehouse_id, quantity, order_id=None, remark=''):
        """预留库存"""
        with transaction.atomic():
            inventory = Inventory.objects.select_for_update().get(
                sku_id=sku_id,
                warehouse_id=warehouse_id
            )
            
            if inventory.available_quantity < quantity:
                raise ValueError(f'库存不足，可用库存: {inventory.available_quantity}')
            
            # 更新预留数量
            inventory.reserved_quantity += quantity
            inventory.save()
            
            # 记录日志
            InventoryLog.objects.create(
                sku_id=sku_id,
                warehouse_id=warehouse_id,
                log_type='reserve',
                quantity=quantity,
                before_quantity=inventory.quantity - inventory.reserved_quantity + quantity,
                after_quantity=inventory.available_quantity,
                remark=f'订单预留: {order_id or ""} {remark}'
            )
            
            return inventory
    
    @staticmethod
    def release_inventory(sku_id, warehouse_id, quantity, order_id=None, remark=''):
        """释放预留库存"""
        with transaction.atomic():
            inventory = Inventory.objects.select_for_update().get(
                sku_id=sku_id,
                warehouse_id=warehouse_id
            )
            
            if inventory.reserved_quantity < quantity:
                raise ValueError(f'预留库存不足，预留数量: {inventory.reserved_quantity}')
            
            # 释放预留数量
            inventory.reserved_quantity -= quantity
            inventory.save()
            
            # 记录日志
            InventoryLog.objects.create(
                sku_id=sku_id,
                warehouse_id=warehouse_id,
                log_type='release',
                quantity=quantity,
                before_quantity=inventory.quantity - inventory.reserved_quantity - quantity,
                after_quantity=inventory.available_quantity,
                remark=f'订单释放: {order_id or ""} {remark}'
            )
            
            return inventory
    
    @staticmethod
    def deduct_inventory(sku_id, warehouse_id, quantity, order_id=None, remark=''):
        """扣减库存（支付后）"""
        with transaction.atomic():
            inventory = Inventory.objects.select_for_update().get(
                sku_id=sku_id,
                warehouse_id=warehouse_id
            )
            
            if inventory.reserved_quantity < quantity:
                raise ValueError(f'预留库存不足')
            
            # 扣减库存和预留数量
            inventory.quantity -= quantity
            inventory.reserved_quantity -= quantity
            inventory.save()
            
            # 记录日志
            InventoryLog.objects.create(
                sku_id=sku_id,
                warehouse_id=warehouse_id,
                log_type='out',
                quantity=quantity,
                before_quantity=inventory.quantity + quantity,
                after_quantity=inventory.quantity,
                remark=f'订单出库: {order_id or ""} {remark}'
            )
            
            return inventory
    
    @staticmethod
    def select_warehouse(sku_id, address_province=None, address_city=None):
        """根据订单地址智能选择仓库"""
        # 优先选择同省份的仓库
        warehouses = Warehouse.objects.filter(is_active=True)
        
        if address_province:
            warehouses = warehouses.filter(province=address_province)
        
        if address_city:
            warehouses = warehouses.filter(city=address_city)
        
        # 查找有库存的仓库
        inventories = Inventory.objects.filter(
            sku_id=sku_id,
            warehouse__in=warehouses,
            available_quantity__gt=0
        ).order_by('-available_quantity')
        
        if inventories.exists():
            return inventories.first().warehouse
        
        # 如果没有匹配的仓库，返回有库存的任意仓库
        inventories = Inventory.objects.filter(
            sku_id=sku_id,
            warehouse__is_active=True,
            available_quantity__gt=0
        ).order_by('-available_quantity')
        
        return inventories.first().warehouse if inventories.exists() else None
    
    @staticmethod
    def check_low_stock():
        """检查低库存预警"""
        inventories = Inventory.objects.filter(
            available_quantity__lte=F('min_stock'),
            min_stock__gt=0
        )
        return inventories

    @staticmethod
    def ship_deduct_sku(sku_id, quantity, order_id=None, remark='商家发货出库'):
        """
        发货扣减：同步减少 SKU.stock 与仓库 Inventory（若有）。
        商品管理页展示 sku.stock，必须在发货时扣减。
        """
        if quantity <= 0:
            return
        with transaction.atomic():
            sku = SKU.objects.select_for_update().get(id=sku_id)
            if sku.stock < quantity:
                raise ValueError(f'「{sku.name}」库存不足，当前 {sku.stock}，需发 {quantity}')
            SKU.objects.filter(id=sku_id).update(stock=F('stock') - quantity)

            remain = quantity
            inventories = (
                Inventory.objects.select_for_update()
                .filter(sku_id=sku_id, quantity__gt=0)
                .order_by('-quantity')
            )
            for inv in inventories:
                if remain <= 0:
                    break
                take = min(inv.quantity, remain)
                before = inv.quantity
                inv.quantity -= take
                inv.available_quantity = max(0, inv.quantity - inv.reserved_quantity)
                inv.save(update_fields=['quantity', 'available_quantity', 'updated_time'])
                InventoryLog.objects.create(
                    sku_id=sku_id,
                    warehouse_id=inv.warehouse_id,
                    log_type='out',
                    quantity=take,
                    before_quantity=before,
                    after_quantity=inv.quantity,
                    remark=f'{remark}: {order_id or ""}'.strip(),
                )
                remain -= take
