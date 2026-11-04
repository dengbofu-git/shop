"""File-backed synthetic SQLite for the cross-process MCP integration test only."""
import os
from copy import deepcopy
from support_ai.test_settings import *  # noqa: F401,F403

DATABASES = deepcopy(DATABASES)
DATABASES['default'] = {
    'ENGINE': 'django.db.backends.sqlite3', 'NAME': os.environ['TEA_SAAS_MCP_TEST_DB'],
}
if os.environ.get('TEA_SAAS_MCP_TEST_AI_DB'):
    DATABASES['ai_storage'] = {
        'ENGINE':'django.db.backends.sqlite3', 'NAME':os.environ['TEA_SAAS_MCP_TEST_AI_DB'],
    }
