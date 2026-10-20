from django.db import models
from users.models import UserProfile
from orders.models import OrderInfo


class StorePage(models.Model):
    """One merchant, one storefront; only the explicit published snapshot is public."""
    merchant = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='store_page')
    draft = models.JSONField(default=dict)
    published = models.JSONField(null=True, blank=True)
    is_published = models.BooleanField(default=False)
    revision = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'supplier_store_page'
        verbose_name = '店铺页面'
        verbose_name_plural = verbose_name


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
