from django.urls import path
from . import views

urlpatterns = [
    path('list', views.InventoryListView.as_view(), name='inventory_list'),
    path('warehouses', views.WarehouseListView.as_view(), name='warehouse_list'),
]
