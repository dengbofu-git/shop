"""File-backed synthetic commerce plus a uniquely named disposable PostgreSQL DB."""
import os
import re

from .test_settings import *  # noqa: F401,F403
from tea_saas.settings import DATABASES as LIVE_DATABASES

name = os.environ['TEA_SAAS_MCP_TEST_PG']
if not re.fullmatch(r'test_mcp_[0-9a-f]{12}', name):
    raise RuntimeError('An isolated MCP PostgreSQL database name is required')
DATABASES['ai_storage'] = dict(LIVE_DATABASES['ai_storage'], NAME=name, CONN_MAX_AGE=0)
