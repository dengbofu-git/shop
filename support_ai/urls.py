from django.urls import path

from .views import chat, conversation_detail, preferences


urlpatterns = [
    path('chat/', chat, name='buyer_support_chat'),
    path('preferences/', preferences, name='buyer_support_preferences'),
    path('conversations/<uuid:conversation_id>/', conversation_detail, name='buyer_support_conversation'),
]
