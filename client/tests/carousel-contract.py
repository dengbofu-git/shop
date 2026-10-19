"""Create an actual carousel response in isolated SQLite; never use business data."""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'support_ai.test_settings'
import django
django.setup()
from django.conf import settings
from django.test import Client
from django.test.utils import setup_databases, teardown_databases
from goods.models import Catalog, SPU, SKU


def main(output):
    assert settings.DATABASES['default']['NAME'] == ':memory:'
    databases = setup_databases(verbosity=0, interactive=False, aliases={'default'})
    try:
        catalog = Catalog.objects.create(name='Tea fixture')
        spu = SPU.objects.create(name='Fixture tea product', catalog=catalog)
        ids = []
        for i in range(8):
            ids.append(SKU.objects.create(spu=spu, name='Spec ' + str(i), caption='Synthetic fixture only',
                       price='66.05', cost_price=10, market_price=70, stock=10, is_launched=True).pk)
        SKU.objects.create(spu=spu, name='No stock', price=1, cost_price=1, market_price=1, stock=0, is_launched=True)
        SKU.objects.create(spu=spu, name='Unlisted', price=1, cost_price=1, market_price=1, stock=10, is_launched=False)
        client = Client()
        response = client.get('/v1/goods/carousel?stable=1&limit=6')
        assert response.status_code == 200
        body = response.json()
        assert [row['skuid'] for row in body['data']] == sorted(ids, reverse=True)[:6]
        for row in body['data']:
            assert row['title'] == spu.name
            assert row['price'] == '66.05'
            assert row['image_url'].endswith('/v1/goods/sku/' + str(row['skuid']) + '/image')
            assert row['link_url'] == 'product_details.html?skuid=' + str(row['skuid'])
        Path(output).write_text(json.dumps(body, indent=2), encoding='utf-8')
        page = client.get('/buyer_dashboard.html').content.decode()
        assert 'id="buyer-carousel"' in page
        assert 'data-carousel-playback' in page and 'data-carousel-retry' in page
        assert page.index('buyer-carousel.js') < page.index('buyer-workbench.js')
        assert 'buyer-carousel.css?v=20261019-carousel' in page
        SKU.objects.all().update(is_launched=False)
        assert client.get('/v1/goods/carousel?stable=1&limit=6').json()['data'] == []
        print('PASS: actual carousel fields, stable selection, stock/launch filtering, empty result and homepage template')
    finally:
        teardown_databases(databases, verbosity=0)


if __name__ == '__main__':
    main(sys.argv[1])
