"""Native MCP processes share one explicitly disposable PostgreSQL database."""
import os
import re
from tea_saas.pg_test_settings import *  # noqa: F401,F403

name = os.environ['TEA_SAAS_MCP_TEST_PG']
if not re.fullmatch(r'test_mcp_[0-9a-f]{12}', name):
    raise RuntimeError('An isolated MCP PostgreSQL database name is required')
DATABASES['default']['NAME'] = name
DATABASES['default']['CONN_MAX_AGE'] = 0
