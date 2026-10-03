from django.urls import path
from . import views

urlpatterns = [
    # 店家资讯管理
    path('create', views.create_news),  # POST - 创建资讯
    path('my', views.my_news),  # GET - 获取我的资讯列表
    path('<int:news_id>/update', views.update_news),  # PUT - 更新资讯
    path('<int:news_id>/delete', views.delete_news),  # DELETE - 删除资讯
    
    # 公共资讯查看
    path('list', views.news_list),  # GET - 获取已发布资讯列表
    path('<int:news_id>/detail', views.news_detail),  # GET - 获取资讯详情
]
