from django.urls import path
from . import views

urlpatterns = [
    path('track/<str:order_id>', views.ShippingTrackView.as_view(), name='shipping_track'),
]
