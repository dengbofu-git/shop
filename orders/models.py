from django.db import models
from goods.models import SKU
from users.models import UserProfile


STATUS_CHOICES = (
    (0, "已关闭"),
    (1, "待付款"),
    (2, "待发货"),
    (3, "待收货"),
    (4, "订单完成")
)

ORDER_TYPE_CHOICES = (
    ('standard', '标准订单'),
    ('trial', '试单'),
    ('presale', '预售订单'),
)

TRIAL_STATUS_CHOICES = (
    (1, "待付款"),
    (2, "待发货"),
    (3, "待收货"),
    (4, "试用中"),
    (5, "试用完成"),
    (6, "退货中"),
    (7, "已退货"),
    (8, "订单完成"),
)

PRESALE_STATUS_CHOICES = (
    (1, "待付定金"),
    (2, "已付定金"),
    (3, "待付尾款"),
    (4, "待发货"),
    (5, "待收货"),
    (6, "订单完成"),
    (7, "已取消"),
)


class OrderInfo(models.Model):
    """订单基础表（支持多态订单）"""
    # 订单表
    # 用户表:订单表 ---> 1:n
    # 订单编号、订单总金额、支付方式、运费、订单状态、收货地址相关字段[反范式]
    user_profile = models.ForeignKey(UserProfile, on_delete=models.CASCADE)
    # 20220301143930007
    order_id = models.CharField(max_length=64, primary_key=True, verbose_name="订单编号")
    # 订单类型
    order_type = models.CharField(max_length=20, choices=ORDER_TYPE_CHOICES, default='standard', verbose_name="订单类型")
    # 订单总金额、商品总数量
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="订单总金额")
    total_count = models.IntegerField(verbose_name="商品总数")
    # 支付方式:1代表支付宝
    pay_method = models.SmallIntegerField(default=1, verbose_name="支付方式")
    # 运费
    freight = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="运费")
    # 订单状态（标准订单使用）
    status = models.SmallIntegerField(verbose_name="订单状态", choices=STATUS_CHOICES, null=True, blank=True)
    buyer_hidden = models.BooleanField(default=False, verbose_name='买家隐藏订单')
    reservation_managed = models.BooleanField(default=False)
    expires_at = models.DateTimeField(null=True, blank=True, db_index=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=30, blank=True, default='')
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_trade_no = models.CharField(max_length=100, null=True, blank=True, unique=True)
    payment_exception = models.CharField(max_length=50, blank=True, default='')
    checkout_request = models.ForeignKey('CheckoutRequest', null=True, blank=True, on_delete=models.PROTECT, related_name='orders')

    # 冗余地址字段
    receiver = models.CharField(verbose_name="收件人", max_length=10)
    address = models.CharField(verbose_name="收件地址", max_length=100)
    receiver_mobile = models.CharField(verbose_name="手机号", max_length=11)
    tag = models.CharField(verbose_name="标签", max_length=10)

    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders_order_info"
    
    def get_status_display_text(self):
        """根据订单类型返回状态显示文本"""
        if self.order_type == 'standard':
            return dict(STATUS_CHOICES).get(self.status, '未知')
        elif self.order_type == 'trial':
            return dict(TRIAL_STATUS_CHOICES).get(self.trialorder.status if hasattr(self, 'trialorder') else None, '未知')
        elif self.order_type == 'presale':
            return dict(PRESALE_STATUS_CHOICES).get(self.presaleorder.status if hasattr(self, 'presaleorder') else None, '未知')
        return '未知'


class StandardOrder(models.Model):
    """标准订单（继承OrderInfo的所有字段）"""
    order_info = models.OneToOneField(OrderInfo, on_delete=models.CASCADE, related_name='standardorder')
    
    class Meta:
        db_table = "orders_standard_order"
    
    def __str__(self):
        return f"标准订单: {self.order_info.order_id}"


class TrialOrder(models.Model):
    """试单（试用订单，支持退货）"""
    order_info = models.OneToOneField(OrderInfo, on_delete=models.CASCADE, related_name='trialorder')
    status = models.SmallIntegerField(verbose_name="试单状态", choices=TRIAL_STATUS_CHOICES, default=1)
    trial_days = models.IntegerField(verbose_name="试用天数", default=7)
    trial_start_time = models.DateTimeField(verbose_name="试用开始时间", null=True, blank=True)
    trial_end_time = models.DateTimeField(verbose_name="试用结束时间", null=True, blank=True)
    return_reason = models.TextField(verbose_name="退货原因", blank=True, null=True)
    return_time = models.DateTimeField(verbose_name="退货时间", null=True, blank=True)
    
    class Meta:
        db_table = "orders_trial_order"
    
    def __str__(self):
        return f"试单: {self.order_info.order_id}"


class PreSaleOrder(models.Model):
    """预售订单（设计预售单，支持定金模式）"""
    order_info = models.OneToOneField(OrderInfo, on_delete=models.CASCADE, related_name='presaleorder')
    status = models.SmallIntegerField(verbose_name="预售订单状态", choices=PRESALE_STATUS_CHOICES, default=1)
    deposit_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="定金金额")
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="尾款金额")
    deposit_paid = models.BooleanField(default=False, verbose_name="是否已付定金")
    balance_paid = models.BooleanField(default=False, verbose_name="是否已付尾款")
    deposit_pay_time = models.DateTimeField(verbose_name="定金支付时间", null=True, blank=True)
    balance_pay_time = models.DateTimeField(verbose_name="尾款支付时间", null=True, blank=True)
    delivery_date = models.DateField(verbose_name="预计发货日期", null=True, blank=True)
    
    class Meta:
        db_table = "orders_presale_order"
    
    def __str__(self):
        return f"预售订单: {self.order_info.order_id}"


class OrderGoods(models.Model):
    """
    订单商品表
    订单表:订单商品表 ---> 1:n
    SKU表:订单商品表 ---> 1:n
    """
    order_info = models.ForeignKey(OrderInfo, on_delete=models.CASCADE)
    sku = models.ForeignKey(SKU, on_delete=models.PROTECT)
    merchant_snapshot = models.ForeignKey(UserProfile, on_delete=models.PROTECT, null=True, blank=True,
                                          related_name='sold_order_items')
    purchase_snapshot = models.JSONField(default=dict, blank=True)

    # 数量、单价
    count = models.IntegerField(default=1, verbose_name="数量")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="单价")

    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "orders_order_goods"

    def save(self, *args, **kwargs):
        # Only new purchases establish historical ownership. Existing rows are not guessed/backfilled.
        if self._state.adding and self.sku_id:
            sku = self.sku
            self.merchant_snapshot_id = sku.spu.merchant_id
            self.purchase_snapshot = {
                'origin': 'purchase', 'spu_id': sku.spu_id, 'sku_id': sku.pk,
                'product_name': sku.spu.name, 'specification': sku.name,
                'merchant_id': sku.spu.merchant_id,
                'merchant_name': sku.spu.merchant.shop_name if sku.spu.merchant_id else '',
            }
        super().save(*args, **kwargs)


class CheckoutRequest(models.Model):
    user = models.ForeignKey(UserProfile, on_delete=models.PROTECT)
    request_id = models.CharField(max_length=64)
    fingerprint = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'request_id'], name='checkout_user_request_unique')]


class StockHold(models.Model):
    item = models.ForeignKey(OrderGoods, on_delete=models.PROTECT, related_name='stock_holds')
    inventory = models.ForeignKey('inventory.Inventory', on_delete=models.PROTECT, related_name='order_holds')
    quantity = models.PositiveIntegerField()
    state = models.CharField(max_length=12, default='reserved', choices=[('reserved','待付预留'),('paid','已付预留'),('consumed','已出库'),('released','已释放')])
    released_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['item', 'inventory'], name='hold_item_warehouse_unique'),
                       models.CheckConstraint(check=models.Q(quantity__gt=0), name='hold_quantity_positive')]


class ReservationPolicy(models.Model):
    merchant = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='reservation_policy')
    ttl_seconds = models.PositiveIntegerField(default=600)
    max_unpaid_quantity = models.PositiveIntegerField(default=100)
    max_unpaid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=20000)
    max_stock_percent = models.PositiveIntegerField(default=50)


class CheckoutThrottle(models.Model):
    # HMAC of the server-observed source IP; no raw IP or client-supplied proxy header.
    key = models.CharField(max_length=64, primary_key=True)
    window_start = models.DateTimeField()
    attempts = models.PositiveIntegerField(default=0)
