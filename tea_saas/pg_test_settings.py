"""One disposable PostgreSQL database. Port must be supplied by the test runner."""
import os
from support_ai.test_settings import *  # noqa: F401,F403
from tea_saas.database import postgres_config

_port = int(os.environ['TEA_SAAS_PG_TEST_PORT'])
DATABASES = {'default': postgres_config({
    'POSTGRES_HOST':'127.0.0.1', 'POSTGRES_PORT':str(_port),
    'POSTGRES_NAME':'unified_fixture', 'POSTGRES_USER':'postgres',
    'POSTGRES_PASSWORD':os.environ['TEA_SAAS_PG_TEST_PASSWORD'],
})}
DATABASES['default']['TEST'] = {'NAME':'test_tea_saas_unified'}
AI_STORAGE_DB_ALIAS = 'default'
TEA_SAAS_DATABASE_MODE = 'unified'
