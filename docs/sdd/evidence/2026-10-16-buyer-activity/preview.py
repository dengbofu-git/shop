"""Disposable local UI verification: no business database or external services.

Run with the project Python environment, then open http://127.0.0.1:8001/__preview__.
Stop with Ctrl+C. Only synthetic users/products are written, to a temporary SQLite DB.
"""
import os
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)
os.environ['DJANGO_SETTINGS_MODULE'] = 'support_ai.test_settings'
os.environ['JWT_SECRET_KEY'] = 'disposable-buyer-activity-preview'
os.environ['PYTHONDONTWRITEBYTECODE'] = '1'

import django
from django.conf import settings

temporary = tempfile.TemporaryDirectory(prefix='dadashop-activity-')
settings.DATABASES['default']['NAME'] = str(Path(temporary.name) / 'preview.sqlite3')
settings.DEBUG = True
django.setup()

from django.core.management import call_command
call_command('migrate', database='default', verbosity=0)

from dadashop.utils import jwt_encode
from goods.models import Catalog, Favorite, SKU, SPU
from users.models import UserProfile

user = UserProfile.objects.create(username='preview', is_active=True)
catalog = Catalog.objects.create(name='红茶')
spu = SPU.objects.create(name='英德红茶 · 验证茶品', catalog=catalog)
for i in range(14):
    sku = SKU.objects.create(spu=spu, name=f'{100 + i * 25}g 礼盒', caption='合成验证商品',
                             price=38 + i, cost_price=20, market_price=60)
    Favorite.objects.create(user=user, sku=sku)

from django.http import HttpResponse
from django.urls import path
from dadashop.urls import urlpatterns as business_urls
import json

encoded = jwt_encode({'id': user.id})
if isinstance(encoded, bytes):
    encoded = encoded.decode()


def bootstrap(request):
    return HttpResponse('<script src="/static/js/auth-storage.js"></script><script>'
                        'AuthStorage.clear();AuthStorage.setToken(' + json.dumps(encoded) + ');'
                        'AuthStorage.setUser("preview");AuthStorage.setUserType("customer");'
                        'location.replace("/myCollect.html");</script>')


urlpatterns = [
    path('__preview__', bootstrap),
    path('static/js/init.js', lambda r: HttpResponse('baseUrl=location.origin;', content_type='text/javascript')),
] + business_urls
settings.ROOT_URLCONF = __name__

from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.wsgi import get_wsgi_application
from wsgiref.simple_server import make_server

# StaticFilesHandler serves init.js before URL resolution, so override that one asset.
static_app = StaticFilesHandler(get_wsgi_application())


def app(environ, start_response):
    if environ.get('PATH_INFO') == '/static/js/init.js':
        start_response('200 OK', [('Content-Type', 'text/javascript')])
        return [b'baseUrl=location.origin;']
    return static_app(environ, start_response)


try:
    print('Synthetic preview ready: http://127.0.0.1:8001/__preview__', flush=True)
    make_server('127.0.0.1', 8001, app).serve_forever()
finally:
    temporary.cleanup()
