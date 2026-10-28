from django.urls import include, path

from .views import chat, conversation_detail, conversation_list, preferences


urlpatterns = [
    path('knowledge/', include('ai_storage.urls')),
    path('chat/', chat, name='buyer_support_chat'),
    path('preferences/', preferences, name='buyer_support_preferences'),
    path('conversations/', conversation_list, name='buyer_support_conversations'),
    path('conversations/<uuid:conversation_id>/', conversation_detail, name='buyer_support_conversation'),
]
