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


def database_config(environ):
    mode = environ.get('TEA_SAAS_DATABASE_MODE', 'unified')
    if mode != 'unified':
        raise ValueError('Only unified PostgreSQL runtime is supported')
    return {'default': postgres_config(environ)}, 'default'
