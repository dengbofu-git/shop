"""SQLite business fixture DB plus a separate test PostgreSQL AI database."""

from .test_settings import *  # noqa: F401,F403
from tea_saas.settings import DATABASES as LIVE_DATABASES

DATABASES['ai_storage'] = dict(LIVE_DATABASES['ai_storage'], TEST={'DEPENDENCIES': [], 'NAME': 'test_tea_saas_ai'})
