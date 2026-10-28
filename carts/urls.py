from django.urls import path
from . import views
from .views import CartsView
from .recommendation_views import RecommendationCartView
urlpatterns = [
    path('<str:username>/recommendations', RecommendationCartView.as_view()),
    path('<str:username>', CartsView.as_view())
]