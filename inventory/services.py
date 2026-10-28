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
            inventory = Inventory.objects.filter(sku_id=sku_id, warehouse_id=warehouse_id, warehouse__is_active=True).first()
            return inventory.available_quantity if inventory else 0
        else:
            # 获取所有仓库的可用库存总和
            total = Inventory.objects.filter(sku_id=sku_id, warehouse__is_active=True).aggregate(
                total=Sum('available_quantity')
            )['total']
            return total or 0
    
    @staticmethod
    def reserve_inventory(sku_id, warehouse_id, quantity, order_id=None, remark=''):
        """预留库存"""
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError('数量必须为正整数')
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
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError('数量必须为正整数')
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
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError('数量必须为正整数')
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
    def locked_ledgers(sku):
        """Caller holds this SKU row. A legacy SKU initializes exactly once."""
        if not Inventory.objects.filter(sku=sku).exists():
            warehouse, _ = Warehouse.objects.get_or_create(code='DEFAULT', defaults={'name':'默认','address':'默认仓库'})
            Inventory.objects.create(sku=sku, warehouse=warehouse, quantity=max(0,sku.stock))
        return list(Inventory.objects.select_for_update().filter(sku=sku).select_related('warehouse').order_by('pk'))

    @staticmethod
    def sync_stock(sku):
        # SKU.stock is physical total, never the sellable source when a ledger exists.
        total = Inventory.objects.filter(sku=sku).aggregate(total=Sum('quantity'))['total'] or 0
        SKU.objects.filter(pk=sku.pk).update(stock=total)
        sku.stock = total

    @staticmethod
    def adjust_stock(sku_id, quantity, warehouse_name=None):
        if isinstance(quantity,bool) or not isinstance(quantity,int) or quantity < 0:
            raise ValueError('库存数量必须为非负整数')
        with transaction.atomic():
            sku = SKU.objects.select_for_update().get(pk=sku_id)
            rows = InventoryService.locked_ledgers(sku)
            if warehouse_name is None:
                if len(rows) != 1:
                    raise ValueError('多仓库存请在库存页面按仓库调整')
                inv = rows[0]
            else:
                candidates = [r for r in rows if (r.warehouse.code=='DEFAULT' if warehouse_name=='默认' else r.warehouse.name==warehouse_name)]
                if len(candidates) != 1:
                    raise ValueError('仓库不存在或名称不唯一')
                inv = candidates[0]
            if quantity < inv.reserved_quantity:
                raise ValueError('新库存不能低于已预留数量，请先处理关联订单')
            before = inv.quantity
            inv.quantity=quantity
            inv.save(update_fields=['quantity','available_quantity','updated_time'])
            InventoryLog.objects.create(sku=sku,warehouse=inv.warehouse,log_type='adjust',quantity=abs(quantity-before),before_quantity=before,after_quantity=quantity,remark='商家调整库存')
            InventoryService.sync_stock(sku)
            return sku.stock

    @staticmethod
    def ship_deduct_sku(sku_id, quantity, order_id=None, remark='历史订单发货出库'):
        """Legacy orders may consume only unreserved stock; managed orders use their holds."""
        if isinstance(quantity,bool) or not isinstance(quantity,int) or quantity <= 0:
            raise ValueError('数量必须为正整数')
        with transaction.atomic():
            sku=SKU.objects.select_for_update().get(pk=sku_id)
            rows=InventoryService.locked_ledgers(sku)
            if sum(r.available_quantity for r in rows if r.warehouse.is_active) < quantity:
                raise ValueError('库存不足，不能占用其他订单已预留的库存')
            remain=quantity
            for inv in rows:
                if not inv.warehouse.is_active:continue
                take=min(inv.available_quantity,remain)
                if not take:continue
                before=inv.quantity;inv.quantity-=take
                inv.save(update_fields=['quantity','available_quantity','updated_time'])
                InventoryLog.objects.create(sku=sku,warehouse=inv.warehouse,log_type='out',quantity=take,before_quantity=before,after_quantity=inv.quantity,remark='%s: %s'%(remark,order_id or ''))
                remain-=take
            InventoryService.sync_stock(sku)
