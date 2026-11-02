"""SQLite business fixture DB plus a separate test PostgreSQL AI database."""
import os
from copy import deepcopy

from .test_settings import *  # noqa: F401,F403
from tea_saas.database import postgres_config

DATABASES = deepcopy(DATABASES)
DATABASES['ai_storage'] = dict(postgres_config(os.environ, 'AI_POSTGRES'), TEST={'DEPENDENCIES': [], 'NAME': 'test_tea_saas_ai'})
