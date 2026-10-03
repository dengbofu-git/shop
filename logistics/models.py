from django.db import models
from orders.models import OrderInfo


class LogisticsProvider(models.Model):
    """物流供应商表"""
    name = models.CharField(max_length=50, verbose_name='物流公司名称')
    code = models.CharField(max_length=20, verbose_name='物流代码', unique=True)
    api_url = models.URLField(verbose_name='API地址', blank=True, null=True)
    api_key = models.CharField(max_length=100, verbose_name='API密钥', blank=True, null=True)
    contact_phone = models.CharField(max_length=20, verbose_name='联系电话', blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'logistics_provider'
        verbose_name = '物流供应商'
        verbose_name_plural = verbose_name
    
    def __str__(self):
        return self.name


class ShippingOrder(models.Model):
    """物流订单表"""
    STATUS_CHOICES = (
        (1, '待发货'),
        (2, '已发货'),
        (3, '运输中'),
        (4, '派送中'),
        (5, '已签收'),
        (6, '异常'),
    )
    
    order_info = models.ForeignKey(OrderInfo, on_delete=models.CASCADE, verbose_name='订单')
    provider = models.ForeignKey(LogisticsProvider, on_delete=models.CASCADE, verbose_name='物流供应商')
    tracking_number = models.CharField(max_length=50, verbose_name='运单号', unique=True)
    status = models.SmallIntegerField(verbose_name='物流状态', choices=STATUS_CHOICES, default=1)
    shipping_fee = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='运费', default=0)
    receiver_name = models.CharField(max_length=50, verbose_name='收件人')
    receiver_phone = models.CharField(max_length=20, verbose_name='收件人电话')
    receiver_address = models.CharField(max_length=200, verbose_name='收件地址')
    weight = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='重量(kg)', default=0)
    remark = models.TextField(verbose_name='备注', blank=True, null=True)
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'logistics_shipping_order'
        verbose_name = '物流订单'
        verbose_name_plural = verbose_name
    
    def __str__(self):
        return f"{self.tracking_number} - {self.order_info.order_id}"


class ShippingTrack(models.Model):
    """物流追踪表"""
    shipping_order = models.ForeignKey(ShippingOrder, on_delete=models.CASCADE, verbose_name='物流订单')
    status = models.SmallIntegerField(verbose_name='状态')
    status_text = models.CharField(max_length=100, verbose_name='状态描述')
    location = models.CharField(max_length=100, verbose_name='位置', blank=True, null=True)
    remark = models.TextField(verbose_name='备注', blank=True, null=True)
    
    created_time = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'logistics_shipping_track'
        verbose_name = '物流追踪'
        verbose_name_plural = verbose_name
        ordering = ['-created_time']
    
    def __str__(self):
        return f"{self.shipping_order.tracking_number} - {self.status_text}"
