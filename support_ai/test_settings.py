"""Isolated test database; never connect to the configured business MySQL/Redis."""

from dadashop.settings import *  # noqa: F401,F403

DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}}
DATABASES['ai_storage'] = {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:', 'TEST': {'DEPENDENCIES': []}}
CACHES = {
    'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
    'carts': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'},
}
ALLOWED_HOSTS = ['testserver', '127.0.0.1']
SUPPORT_API_KEY = 'test-model-never-called'
