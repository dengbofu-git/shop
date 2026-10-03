from django.db import models


def sku_image_upload_to(instance, filename):
    """SKU 默认图片保存路径：sku/{sku_id}/{filename}"""
    if hasattr(instance, 'pk') and instance.pk:
        return f'sku/{instance.pk}/{filename}'
    if hasattr(instance, 'id') and instance.id:
        return f'sku/{instance.id}/{filename}'
    return f'sku/temp/{filename}'


def sku_extra_image_upload_to(instance, filename):
    """SKUImage 图片保存路径：sku/{sku_id}/{filename}"""
    sku_id = instance.sku_id if hasattr(instance, 'sku_id') else (instance.sku.id if instance.sku else 0)
    return f'sku/{sku_id}/{filename}'


class CarouselSlide(models.Model):
    """
    首页走马灯/轮播配置
    超级终端可配置展示内容
    """
    title = models.CharField(max_length=100, verbose_name='标题/描述')
    link_url = models.CharField(max_length=255, blank=True, null=True, verbose_name='跳转链接')
    link_type = models.CharField(max_length=20, default='catalog', verbose_name='链接类型')  # catalog, sku, url
    sort_order = models.IntegerField(default=0, verbose_name='排序')
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'goods_carousel_slide'
        verbose_name = '轮播项'
        verbose_name_plural = verbose_name
        ordering = ['sort_order', 'id']

    def __str__(self):
        return self.title


class Catalog(models.Model):
    """
    商品类别
    """
    name = models.CharField(max_length=10, verbose_name='类别名称')
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "goods_catalog"
        verbose_name = '商品类别'
        verbose_name_plural = verbose_name


class Brand(models.Model):
    """
    品牌
    """

    name = models.CharField(max_length=20, verbose_name='商品名称')
    logo = models.ImageField(verbose_name='Logo图片', upload_to='brand', blank=True, null=True)
    first_letter = models.CharField(max_length=1, verbose_name='品牌首字母')
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "goods_brand"
        verbose_name = '品牌'
        verbose_name_plural = verbose_name


class SPU(models.Model):
    name = models.CharField(max_length=50, verbose_name='名称')
    sales = models.IntegerField(default=0, verbose_name='商品销量')
    comments = models.IntegerField(default=0, verbose_name='评价数量')
    brand = models.ForeignKey(Brand, verbose_name='品牌', on_delete=models.CASCADE, null=True, blank=True)
    catalog = models.ForeignKey(Catalog, verbose_name='商品类别', on_delete=models.CASCADE)
    # 店家关联（只有店家可以创建商品）
    merchant = models.ForeignKey('users.UserProfile', on_delete=models.CASCADE, verbose_name='店家', 
                                 null=True, blank=True, related_name='spus')
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "goods_spu"
        verbose_name = '商品系列'
        verbose_name_plural = '商品系列'


class SPUSaleAttr(models.Model):
    """
    SPU销售属性表
    """
    spu = models.ForeignKey(SPU, on_delete=models.CASCADE)
    name = models.CharField(max_length=20, verbose_name='SPU属性名称')
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'goods_spu_sale_attr'
        verbose_name = 'SPU销售属性'
        verbose_name_plural = verbose_name


class SaleAttrValue(models.Model):
    """
    销售属性值表
    """
    spu_sale_attr = models.ForeignKey(SPUSaleAttr, on_delete=models.CASCADE, verbose_name='销售属性')
    name = models.CharField(max_length=20, verbose_name='销售属性值名称')
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'goods_sale_attr_value'
        verbose_name = '销售属性值'
        verbose_name_plural = verbose_name


class SKU(models.Model):
    """
    SKU
    """
    name = models.CharField(max_length=50, verbose_name='商品名称')
    caption = models.CharField(max_length=100, verbose_name='商品副标题')
    spu = models.ForeignKey(SPU, on_delete=models.CASCADE, verbose_name='商品系列')
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='单价')
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='进价')
    market_price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='市场价')
    stock = models.IntegerField(default=0, verbose_name='库存')
    sales = models.IntegerField(default=0, verbose_name='销量')
    comments = models.IntegerField(default=0, verbose_name='评价数')
    is_launched = models.BooleanField(default=True, verbose_name='是否上架销售')
    is_recommended = models.BooleanField(default=False, verbose_name='选择')
    default_image_url = models.ImageField(verbose_name='默认图片', upload_to=sku_image_upload_to, null=True, blank=True)
    version = models.IntegerField(default=0, verbose_name="库存版本号")
    sale_attr_value = models.ManyToManyField(SaleAttrValue)
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "goods_sku"
        verbose_name = '推荐商品'
        verbose_name_plural = '推荐商品'

    def __str__(self):
        return '%s: %s' % (self.id, self.name)


class SKUImage(models.Model):
    """
        SKU图片
    """
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, verbose_name='sku')
    image = models.ImageField(verbose_name='图片路径', upload_to=sku_extra_image_upload_to)
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'goods_sku_image'
        verbose_name = 'SKU图片'
        verbose_name_plural = verbose_name


class SPUSpec(models.Model):
    """
    SPU规格表
    """
    spu = models.ForeignKey(SPU, on_delete=models.CASCADE)
    name = models.CharField(max_length=20, verbose_name='SPU规格名称')
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'goods_spu_spec'
        verbose_name = 'SPU规格'
        verbose_name_plural = verbose_name


class SKUSpecValue(models.Model):
    """
    SKU规格属性表
    """
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE)
    spu_spec = models.ForeignKey(SPUSpec, on_delete=models.CASCADE)
    name = models.CharField(max_length=20, verbose_name='SKU规格名称值')
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'goods_spu_spec_value'
        verbose_name = 'SKU规格属性值表'
        verbose_name_plural = verbose_name


class ProductTemplate(models.Model):
    """
    商品模板表
    支持不同品类的商品模板
    """
    name = models.CharField(max_length=50, verbose_name='模板名称')
    catalog = models.ForeignKey(Catalog, on_delete=models.CASCADE, verbose_name='商品类别', null=True, blank=True)
    description = models.TextField(verbose_name='模板描述', blank=True, null=True)
    is_active = models.BooleanField(default=True, verbose_name='是否启用')
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'goods_product_template'
        verbose_name = '商品模板'
        verbose_name_plural = verbose_name
    
    def __str__(self):
        return self.name


class ProductAttribute(models.Model):
    """
    商品属性表
    动态属性定义（如：颜色、尺寸、材质等）
    """
    ATTRIBUTE_TYPE_CHOICES = (
        ('text', '文本'),
        ('number', '数字'),
        ('select', '选择'),
        ('multiselect', '多选'),
        ('boolean', '布尔值'),
        ('date', '日期'),
    )
    
    template = models.ForeignKey(ProductTemplate, on_delete=models.CASCADE, verbose_name='商品模板', null=True, blank=True)
    catalog = models.ForeignKey(Catalog, on_delete=models.CASCADE, verbose_name='商品类别', null=True, blank=True)
    name = models.CharField(max_length=50, verbose_name='属性名称')
    code = models.CharField(max_length=50, verbose_name='属性代码', unique=True)
    attribute_type = models.CharField(max_length=20, choices=ATTRIBUTE_TYPE_CHOICES, verbose_name='属性类型')
    is_required = models.BooleanField(default=False, verbose_name='是否必填')
    is_filterable = models.BooleanField(default=False, verbose_name='是否可筛选')
    is_searchable = models.BooleanField(default=False, verbose_name='是否可搜索')
    sort_order = models.IntegerField(default=0, verbose_name='排序')
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'goods_product_attribute'
        verbose_name = '商品属性'
        verbose_name_plural = verbose_name
    
    def __str__(self):
        return self.name


class ProductAttributeValue(models.Model):
    """
    商品属性值表
    属性值存储
    """
    attribute = models.ForeignKey(ProductAttribute, on_delete=models.CASCADE, verbose_name='属性')
    spu = models.ForeignKey(SPU, on_delete=models.CASCADE, verbose_name='SPU', null=True, blank=True)
    sku = models.ForeignKey(SKU, on_delete=models.CASCADE, verbose_name='SKU', null=True, blank=True)
    value_text = models.CharField(max_length=255, verbose_name='文本值', blank=True, null=True)
    value_number = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='数字值', null=True, blank=True)
    value_boolean = models.BooleanField(verbose_name='布尔值', null=True, blank=True)
    value_date = models.DateField(verbose_name='日期值', null=True, blank=True)
    
    created_time = models.DateTimeField(auto_now_add=True)
    updated_time = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'goods_product_attribute_value'
        verbose_name = '商品属性值'
        verbose_name_plural = verbose_name
    
    def get_value(self):
        """根据属性类型返回对应的值"""
        if self.attribute.attribute_type == 'text':
            return self.value_text
        elif self.attribute.attribute_type == 'number':
            return self.value_number
        elif self.attribute.attribute_type == 'boolean':
            return self.value_boolean
        elif self.attribute.attribute_type == 'date':
            return self.value_date
        return self.value_text
    
    def __str__(self):
        return f"{self.attribute.name}: {self.get_value()}"
