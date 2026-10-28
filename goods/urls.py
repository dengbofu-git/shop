from django.urls import path
from . import views
from . import merchant_views
from . import activity_views
from . import product_import_views

urlpatterns = [
    path('merchant/imports/template', product_import_views.template, name='product_import_template'),
    path('merchant/imports', product_import_views.upload, name='product_import_upload'),
    path('merchant/imports/<uuid:job_id>', product_import_views.detail, name='product_import_detail'),
    path('merchant/imports/<uuid:job_id>/commit', product_import_views.commit, name='product_import_commit'),
    path('favorites', activity_views.favorites),
    path('favorites/<int:sku_id>', activity_views.favorite),
    path('merchant-favorites', activity_views.merchant_favorites),
    path('merchant-favorites/<int:merchant_id>', activity_views.merchant_favorite),
    path('recent', activity_views.recent),
    path('recent/<int:sku_id>', activity_views.recent_item),
    # 客户商品查看
    path('carousel', views.carousel),
    path('recommended-products', views.recommended_products),
    path('index', views.index),
    path('catalogs/<int:id>', views.catalogs),
    path('detail/<int:id>', views.detail),
    path('sku/<int:sku_id>/image', views.sku_image),
    path('sku', views.sku),
    
    # 店家商品管理
    path('merchant/brands-catalogs', merchant_views.brands_and_catalogs),  # GET - 品牌和分类
    path('merchant/spu/create', merchant_views.create_spu),  # POST - 创建SPU
    path('merchant/spu/<int:spu_id>', merchant_views.spu_detail),  # PUT - 修改SPU, DELETE - 删除SPU
    path('merchant/sku/create', merchant_views.create_sku),  # POST - 创建SKU
    path('merchant/sku/<int:sku_id>/status', merchant_views.update_sku_status),  # PUT - 更新SKU状态(兼容)
    path('merchant/sku/<int:sku_id>/image', merchant_views.upload_sku_image),  # POST - 上传SKU商品图片
    path('merchant/sku/<int:sku_id>', merchant_views.sku_detail),  # PUT - 修改SKU, DELETE - 删除SKU
    path('merchant/products', merchant_views.my_products),  # GET - 获取我的商品列表
]
