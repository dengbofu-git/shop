"""File-backed synthetic commerce plus a uniquely named disposable PostgreSQL DB."""
import os
import re
from copy import deepcopy

from .test_settings import *  # noqa: F401,F403
from tea_saas.database import postgres_config

name = os.environ['TEA_SAAS_MCP_TEST_PG']
if not re.fullmatch(r'test_mcp_[0-9a-f]{12}', name):
    raise RuntimeError('An isolated MCP PostgreSQL database name is required')
DATABASES = deepcopy(DATABASES)
DATABASES['ai_storage'] = dict(postgres_config(os.environ, 'AI_POSTGRES'), NAME=name, CONN_MAX_AGE=0)
