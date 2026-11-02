"""AI data participates in the default transaction in the unified runtime."""
from django.conf import settings


def alias():
    # Existing, already-running split workers can finish before the cutover.
    return getattr(settings, 'AI_STORAGE_DB_ALIAS', 'ai_storage')
