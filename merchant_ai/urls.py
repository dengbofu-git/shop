from django.urls import path

from . import views


app_name = 'merchant_ai'
urlpatterns = [
    path('status/', views.status, name='status'),
]
