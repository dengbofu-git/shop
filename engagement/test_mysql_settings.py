"""Opt-in isolated MySQL tests; neither NAME nor TEST.NAME is the business schema."""
import copy
import secrets

from support_ai.test_settings import *  # noqa: F401,F403
from tea_saas.settings import DATABASES as CONFIGURED_DATABASES

DATABASES = copy.deepcopy(DATABASES)
_name = 'test_engagement_' + secrets.token_hex(6)
assert _name not in [value['NAME'] for value in CONFIGURED_DATABASES.values()]
DATABASES['default'] = copy.deepcopy(CONFIGURED_DATABASES['default'])
DATABASES['default']['NAME'] = _name
DATABASES['default']['TEST'] = {'NAME': _name, 'DEPENDENCIES': []}
