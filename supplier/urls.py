from django.urls import path
from . import views

urlpatterns = [
    path('analytics', views.SupplierAnalyticsView.as_view(), name='supplier_analytics'),
    path('orders/delete', views.SupplierOrderDeleteView.as_view(), name='supplier_order_delete'),
    path('orders/<str:order_id>/ship', views.SupplierOrderShipView.as_view(), name='supplier_order_ship'),
    path('orders', views.SupplierOrderListView.as_view(), name='supplier_orders'),
    path('inventory/delete', views.SupplierInventoryDeleteView.as_view(), name='supplier_inventory_delete'),
    path('inventory/update', views.SupplierInventoryUpdateView.as_view(), name='supplier_inventory_update'),
    path('inventory', views.SupplierInventoryView.as_view(), name='supplier_inventory'),
    path('settlement', views.SupplierSettlementView.as_view(), name='supplier_settlement'),
]
