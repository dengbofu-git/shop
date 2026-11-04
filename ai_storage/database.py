"""AI data participates in the default transaction in the unified runtime."""
from django.conf import settings


def alias():
    # Alternate aliases are supplied explicitly by isolated test fixtures.
    return getattr(settings, 'AI_STORAGE_DB_ALIAS', 'default')
