"""Run activity tests against an automatically deleted, uniquely named MySQL DB."""
from copy import deepcopy
from uuid import uuid4

from support_ai.test_settings import *  # noqa: F401,F403
from dadashop.settings import DATABASES as BUSINESS_DATABASES

DATABASES['default'] = deepcopy(BUSINESS_DATABASES['default'])
DATABASES['default']['TEST'] = {'NAME': 'test_buyer_activity_' + uuid4().hex[:12]}
