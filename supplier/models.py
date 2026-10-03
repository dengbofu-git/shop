from django.db import models
from users.models import UserProfile
from orders.models import OrderInfo


class SupplierSettlement(models.Model):
    """供应商结算表"""
    supplier = models.ForeignKey(UserProfile, on_delete=models.CASCADE, verbose_name='供应商')
    order_info = models.ForeignKey(OrderInfo, on_delete=models.CASCADE, verbose_name='订单')
    amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='结算金额')
    status = models.CharField(max_length=20, choices=(
        ('pending', '待结算'),
        ('settled', '已结算'),
        ('cancelled', '已取消'),
    ), default='pending', verbose_name='结算状态')
    settlement_time = models.DateTimeField(verbose_name='结算时间', null=True, blank=True)
    remark = models.TextField(verbose_name='备注', blank=True, null=True)
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'supplier_settlement'
        verbose_name = '供应商结算'
        verbose_name_plural = verbose_name
