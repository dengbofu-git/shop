"""File-backed synthetic SQLite for the cross-process MCP integration test only."""
import os
from support_ai.test_settings import *  # noqa: F401,F403

DATABASES['default'] = {
    'ENGINE': 'django.db.backends.sqlite3', 'NAME': os.environ['TEA_SAAS_MCP_TEST_DB'],
}
if os.environ.get('TEA_SAAS_MCP_TEST_AI_DB'):
    DATABASES['ai_storage'] = {
        'ENGINE':'django.db.backends.sqlite3', 'NAME':os.environ['TEA_SAAS_MCP_TEST_AI_DB'],
    }
if os.environ.get('TEA_SAAS_MCP_TEST_MYSQL_PORT'):
    test_port = int(os.environ['TEA_SAAS_MCP_TEST_MYSQL_PORT'])
    if not 1024 <= test_port <= 65535:
        raise RuntimeError('Invalid disposable MySQL port')
    DATABASES['default'] = {
        'ENGINE':'django.db.backends.mysql', 'NAME':'test_mcp', 'HOST':'127.0.0.1',
        'PORT':test_port, 'USER':'mcp_fixture', 'PASSWORD':os.environ['TEA_SAAS_MCP_TEST_MYSQL_PASSWORD'],
        'OPTIONS':{'charset':'utf8mb4','connect_timeout':5,'read_timeout':10,'write_timeout':10},
    }
