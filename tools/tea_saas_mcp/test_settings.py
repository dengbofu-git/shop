"""File-backed synthetic SQLite for the cross-process MCP integration test only."""
import os
from support_ai.test_settings import *  # noqa: F401,F403

DATABASES['default'] = {
    'ENGINE': 'django.db.backends.sqlite3', 'NAME': os.environ['TEA_SAAS_MCP_TEST_DB'],
}
