from django.urls import path
from . import views

urlpatterns = [
    path('users', views.UserManagementView.as_view(), name='admin_users'),
]
