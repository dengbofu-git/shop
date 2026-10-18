from django.urls import path
from . import views
from . import agent_views

urlpatterns = [
    path('overview', views.platform_overview, name='admin_overview'),
    path('users', views.UserManagementView.as_view(), name='admin_users'),
    path('agent/settings', agent_views.agent_settings, name='admin_agent_settings'),
    path('agent/models', agent_views.agent_models, name='admin_agent_models'),
    path('agent/retrieval-status', agent_views.agent_retrieval_status, name='admin_agent_retrieval_status'),
    path('agent/monitoring', agent_views.agent_monitoring, name='admin_agent_monitoring'),
    path('agent/traces/<str:trace_id>', agent_views.agent_trace, name='admin_agent_trace'),
]
