from django.contrib import admin
from django.contrib.auth.models import Group
from django import forms
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages
from .models import CarouselSlide, SKU


LINK_TYPE_CHOICES = (
    ('catalog', '商品分类页面'),
    ('sku', '商品详情页面'),
    ('url', '自定义网页地址'),
)


class CarouselSlideAdminForm(forms.ModelForm):
    link_type = forms.ChoiceField(choices=LINK_TYPE_CHOICES, label='点击后跳转到')

    class Meta:
        model = CarouselSlide
        fields = '__all__'


@admin.register(CarouselSlide)
class CarouselSlideAdmin(admin.ModelAdmin):
    """首页轮播配置 - 从可售商品中选择"""
    form = CarouselSlideAdminForm
    list_display = ('title', 'link_type_display', 'link_url', 'sort_order', 'is_active', 'updated_time')
    list_editable = ('sort_order', 'is_active')
    # 删除过滤器
    # list_filter = ('link_type', 'is_active')
    search_fields = ('title', 'link_url')
    ordering = ('sort_order', 'id')
    list_per_page = 20
    
    # 禁用添加按钮
    def has_add_permission(self, request):
        return False

    fieldsets = (
        (None, {
            'fields': ('title', 'link_type', 'link_url', 'sort_order', 'is_active'),
            'description': '轮播项通过管理后台终端页面添加，请从可售商品中选择。'
        }),
    )

    def link_type_display(self, obj):
        d = {'catalog': '商品分类页面', 'sku': '商品详情页面', 'url': '自定义网页地址'}
        return d.get(obj.link_type, obj.link_type)
    link_type_display.short_description = '跳转类型'


# 取消注册Group模型（如果已注册）
try:
    admin.site.unregister(Group)
except admin.sites.NotRegistered:
    pass


# 推荐商品管理
@admin.register(SKU)
class RecommendedProductAdmin(admin.ModelAdmin):
    """推荐商品管理 - 从现有可售商品中选择并标记为推荐"""
    list_display = ('name', 'price', 'spu_display', 'catalog_display', 'is_recommended', 'stock', 'sales', 'updated_time')
    list_editable = ('is_recommended',)
    # 删除过滤器部分
    # list_filter = ('is_recommended', 'spu__catalog', 'created_time')
    search_fields = ('name', 'caption', 'spu__name')
    ordering = ('-is_recommended', '-updated_time')
    list_per_page = 50
    
    # 禁用添加新商品功能
    def has_add_permission(self, request):
        return False
    
    # 禁用批量操作（移除左侧勾选框）
    def get_actions(self, request):
        actions = super().get_actions(request)
        if 'delete_selected' in actions:
            del actions['delete_selected']
        return actions
    
    # 只显示可售商品
    def get_queryset(self, request):
        """只显示已上架的可售商品"""
        qs = super().get_queryset(request)
        qs = qs.filter(is_launched=True)  # 只显示已上架的商品
        return qs.select_related('spu', 'spu__catalog', 'spu__brand')
    
    # 编辑页面只允许修改推荐状态
    fieldsets = (
        ('商品信息（只读）', {
            'fields': ('name', 'caption', 'spu', 'price', 'market_price', 'cost_price'),
            'description': '以下信息为只读，如需修改商品信息，请前往商品管理页面。',
        }),
        ('库存与销售（只读）', {
            'fields': ('stock', 'sales', 'comments'),
        }),
        ('推荐设置', {
            'fields': ('is_recommended',),
            'description': '人工推荐标记，供智能客服匹配条件相同后的排序使用；采购页推荐商品按有库存商品的销量排序，不使用此标记。',
        }),
        ('图片（只读）', {
            'fields': ('default_image_url',),
        }),
    )
    
    # 将大部分字段设为只读
    readonly_fields = ('name', 'caption', 'spu', 'price', 'market_price', 'cost_price', 
                       'stock', 'sales', 'comments', 'default_image_url')
    
    # 处理changelist的批量保存
    def changelist_view(self, request, extra_context=None):
        # 如果是POST请求，先统计变更
        changed_count = 0
        changed_names = []
        
        if request.method == 'POST' and '_save' in request.POST:
            # 获取保存前的状态
            queryset = self.get_queryset(request)
            original_data = {}
            for obj in queryset:
                original_data[obj.pk] = {
                    'is_recommended': obj.is_recommended,
                    'name': obj.name
                }
            
            # 调用父类方法处理保存
            response = super().changelist_view(request, extra_context)
            
            # 保存后比较变更
            for pk, original in original_data.items():
                try:
                    obj = self.model.objects.get(pk=pk)
                    if obj.is_recommended != original['is_recommended']:
                        changed_count += 1
                        if obj.is_recommended:
                            changed_names.append(f'"{obj.name}"已设置为推荐商品')
                        else:
                            changed_names.append(f'"{obj.name}"已取消推荐')
                except self.model.DoesNotExist:
                    pass
            
            # 添加消息
            if changed_count > 0:
                # 清除默认消息
                storage = messages.get_messages(request)
                list(storage)  # 消费所有现有消息
                
                if changed_count <= 3:
                    for msg in changed_names:
                        messages.success(request, f'✓ 商品{msg}', extra_tags='bottom-message')
                else:
                    messages.success(request, f'✓ 总共{changed_count}个推荐商品变更成功。', extra_tags='bottom-message')
            
            return response
        
        return super().changelist_view(request, extra_context)
    
    # 保存后显示消息（单个编辑）
    def save_model(self, request, obj, form, change):
        old_value = None
        if change:
            old_obj = self.model.objects.get(pk=obj.pk)
            old_value = old_obj.is_recommended
        
        super().save_model(request, obj, form, change)
        
        if change and old_value is not None:
            if obj.is_recommended != old_value:
                if obj.is_recommended:
                    messages.success(request, f'✓ 商品"{obj.name}"已设置为推荐商品', extra_tags='bottom-message')
                else:
                    messages.success(request, f'✓ 商品"{obj.name}"已取消推荐', extra_tags='bottom-message')
    
    def catalog_display(self, obj):
        """显示商品分类"""
        return obj.spu.catalog.name if obj.spu and obj.spu.catalog else '-'
    catalog_display.short_description = '商品分类'
    
    def spu_display(self, obj):
        """显示商品系列"""
        return obj.spu.name if obj.spu else '-'
    spu_display.short_description = '商品系列'
    
    # 自定义模板以隐藏左侧勾选框并移动消息位置
    change_list_template = 'admin/goods/sku/change_list.html'
