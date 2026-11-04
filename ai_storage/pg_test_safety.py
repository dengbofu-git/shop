"""Admission guard for optional tests that write only to disposable PostgreSQL."""
import os
import re


def require_disposable_postgresql(variable, prefix):
    """Reject unsafe configuration before connecting, then verify the live target."""
    from django.conf import settings
    from django.db import connections

    expected = os.getenv(variable, '')
    if re.fullmatch(re.escape(prefix) + r'[0-9a-f]{24}', expected) is None:
        raise RuntimeError('A dedicated disposable PostgreSQL database is required')
    databases = settings.DATABASES
    if set(databases) != {'default'} or getattr(settings, 'AI_STORAGE_DB_ALIAS', 'default') != 'default':
        raise RuntimeError('Optional database fixtures require one default PostgreSQL connection')
    configured = databases['default']
    engine = 'django.db.backends.postgresql'
    if configured.get('ENGINE') != engine or configured.get('NAME') != expected:
        raise RuntimeError('Unsafe configured PostgreSQL fixture target')
    connection = connections['default']
    if (connection.vendor != 'postgresql' or connection.settings_dict.get('ENGINE') != engine
            or connection.settings_dict.get('NAME') != expected):
        raise RuntimeError('Unsafe PostgreSQL fixture connection')
    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        row = cursor.fetchone()
    if not row or len(row) != 1 or row[0] != expected:
        raise RuntimeError('Actual PostgreSQL fixture database does not match the disposable target')
