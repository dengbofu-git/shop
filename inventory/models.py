from django.db import models
from goods.models import SKU


class Warehouse(models.Model):
    """仓库表"""
    name = models.CharField(max_length=50, verbose_name='仓库名称')
    code = models.CharField(max_length=20, verbose_name='仓库代码', unique=True)
    address = models.CharField(max_length=200, verbose_name='仓库地址')
    province = models.CharField(max_length=50, verbose_name='省份', blank=True, null=True)
    city = models.CharField(max_length=50, verbose_name='城市', blank=True, null=True)
    contact_person = models.CharField(max_length=50, verbose_name='联系人', blank=True, null=True)
    contact_phone = models.CharField(max_length=20, verbose_name='联系电话', blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory_warehouse'
        verbose_name = '仓库'
        verbose_name_plural = verbose_name
    
    def __str__(self):
        return self.name


class Inventory(models.Model):
    """库存表"""
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, verbose_name='SKU')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, verbose_name='仓库')
    quantity = models.IntegerField(default=0, verbose_name='库存数量')
    reserved_quantity = models.IntegerField(default=0, verbose_name='预留数量')
    available_quantity = models.IntegerField(default=0, verbose_name='可用数量')
    min_stock = models.IntegerField(default=0, verbose_name='最低库存预警值')
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'inventory_inventory'
        verbose_name = '库存'
        verbose_name_plural = verbose_name
        unique_together = ('sku', 'warehouse')
    
    def __str__(self):
        return f"{self.sku.name} - {self.warehouse.name}: {self.quantity}"
    
    def save(self, *args, **kwargs):
        """保存时自动计算可用数量"""
        self.available_quantity = self.quantity - self.reserved_quantity
        super().save(*args, **kwargs)


class InventoryLog(models.Model):
    """库存日志表"""
    LOG_TYPE_CHOICES = (
        ('in', '入库'),
        ('out', '出库'),
        ('reserve', '预留'),
        ('release', '释放'),
        ('adjust', '调整'),
    )
    
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, verbose_name='SKU')
    warehouse = models.ForeignKey(Warehouse, on_delete=models.CASCADE, verbose_name='仓库')
    log_type = models.CharField(max_length=20, choices=LOG_TYPE_CHOICES, verbose_name='日志类型')
    quantity = models.IntegerField(verbose_name='数量')
    before_quantity = models.IntegerField(verbose_name='变动前数量')
    after_quantity = models.IntegerField(verbose_name='变动后数量')
    remark = models.TextField(verbose_name='备注', blank=True, null=True)
    operator = models.CharField(max_length=50, verbose_name='操作人', blank=True, null=True)
    
    created_time = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'inventory_inventory_log'
        verbose_name = '库存日志'
        verbose_name_plural = verbose_name
    
    def __str__(self):
        return f"{self.sku.name} - {self.get_log_type_display()}: {self.quantity}"
