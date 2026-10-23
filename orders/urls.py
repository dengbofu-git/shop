from django.urls import path
from . import views
from .checkout_views import cancel_order
urlpatterns = [
    path('<str:username>/advance', views.advance),
    path('<str:username>/confirm-receipt', views.confirm_receipt),
    path('<str:username>/delete', views.delete_order),
    path('<str:username>/cancel', cancel_order),
    path('<str:username>/', views.OrdersView.as_view()),
    path('<str:username>', views.OrdersView.as_view()),
]
