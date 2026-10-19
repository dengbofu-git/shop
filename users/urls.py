from django.urls import path
from . import views
from .views import AddressView, UserProfileView

urlpatterns = [
    path('register', views.register),
    path('login', views.login),
    path('session', views.session_access),
    path('<str:username>/profile', UserProfileView.as_view()),
    path('<str:username>/address', AddressView.as_view()),
    path('<str:username>/address/<int:id>', AddressView.as_view()),
    path('<str:username>/address/default', views.default),
    path('<str:username>/password', views.password_change),
]
