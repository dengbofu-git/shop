from django.urls import path
from . import views

urlpatterns = [
    path('identity', views.identity),
    path('conversations/resolve', views.resolve),
    path('conversations', views.conversations),
    path('conversations/<int:conversation_id>/messages', views.messages),
    path('conversations/<int:conversation_id>/read', views.read_messages),
    path('conversations/<int:conversation_id>/hide', views.hide_conversation),
    path('conversations/<int:conversation_id>/restore', views.restore_conversation),
    path('reviewable-items', views.reviewable_items),
    path('reviews', views.create_review),
    path('reviews/mine', views.own_reviews),
    path('reviews/<int:review_id>/reply', views.reply_review),
    path('reviews/<int:review_id>/report', views.report_review),
    path('products/<int:sku_id>/reviews', views.product_reviews),
    path('moderation', views.moderation_list),
    path('moderation/<int:review_id>', views.moderate_review),
]
