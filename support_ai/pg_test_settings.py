"""SQLite business fixture DB plus a separate test PostgreSQL AI database."""

from .test_settings import *  # noqa: F401,F403
from dadashop.settings import DATABASES as LIVE_DATABASES

DATABASES['ai_storage'] = dict(LIVE_DATABASES['ai_storage'], TEST={'DEPENDENCIES': [], 'NAME': 'test_dadashop_ai'})
