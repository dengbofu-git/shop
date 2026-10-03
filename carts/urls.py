from django.urls import path
from . import views
from .views import CartsView
urlpatterns = [
    path('<str:username>', CartsView.as_view())
]