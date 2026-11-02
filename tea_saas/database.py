"""Explicit database topology. Unified runtime uses a single ORM connection."""


def postgres_config(environ, prefix='POSTGRES'):
    return {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': environ.get(prefix + '_NAME', 'tea_saas' if prefix == 'POSTGRES' else 'tea_saas_ai'),
        'USER': environ.get(prefix + '_USER', 'tea_saas' if prefix == 'POSTGRES' else 'tea_saas_ai'),
        'PASSWORD': environ.get(prefix + '_PASSWORD', ''),
        'HOST': environ.get(prefix + '_HOST', '127.0.0.1'),
        'PORT': int(environ.get(prefix + '_PORT', '5433')),
        'CONN_MAX_AGE': 60,
        'OPTIONS': {'connect_timeout': 5},
    }


def legacy_databases(environ):
    """Source-only bridge and explicit split-database test fixtures."""
    return {
        'default': {
            'ENGINE': 'django.db.backends.mysql',
            'USER': environ['DB_USER'], 'PASSWORD': environ['DB_PASSWORD'],
            'HOST': environ['DB_HOST'], 'PORT': int(environ['DB_PORT']),
            'NAME': environ['DB_NAME'], 'OPTIONS': {'charset': 'utf8mb4'},
        },
        'ai_storage': postgres_config(environ, 'AI_POSTGRES'),
    }


def database_config(environ):
    mode = environ.get('TEA_SAAS_DATABASE_MODE', 'unified')
    if mode == 'unified':
        return {'default': postgres_config(environ)}, 'default'
    if mode == 'legacy':
        return legacy_databases(environ), 'ai_storage'
    raise ValueError('TEA_SAAS_DATABASE_MODE must be unified or legacy')
