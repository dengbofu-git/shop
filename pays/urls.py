from django.urls import path
from . import views
urlpatterns = [
    path('checkout-payment',views.checkout_payment),
    path('notify',views.notify),
]
