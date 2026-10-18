"""Generate the real catalog response from disposable SQLite fixtures for Node QA.

Run from the repository root with the Dadashop Python environment:
python client/tests/catalog-preview-contract.py <output-json-path>
node client/tests/buyer-catalog-preview.test.js <output-json-path>
"""
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
    assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
    configuration = setup_databases(verbosity=0, interactive=False, aliases={'default'})
    try:
        expected = {}
        for name, count in (('\u7ea2\u8336', 16), ('\u7eff\u8336', 14), ('Empty', 0)):
            catalog = Catalog.objects.create(name=name)
            spu = SPU.objects.create(name=name, catalog=catalog)
            ids = set()
            for index in range(count):
                sku = SKU.objects.create(spu=spu, name='Fixture-' + str(index), caption='Synthetic only',
                                         price=5, cost_price=3, market_price=7, stock=10, is_launched=True)
                ids.add(sku.pk)
            SKU.objects.create(spu=spu, name='No stock', price=5, cost_price=3, market_price=7, stock=0)
            SKU.objects.create(spu=spu, name='Unlisted', price=5, cost_price=3, market_price=7,
                               stock=10, is_launched=False)
            if count:
                expected[catalog.pk] = ids
        response = Client().get('/v1/goods/index')
        assert response.status_code == 200
        body = response.json()
        assert body['code'] == 200
        assert {cat['catalog_id'] for cat in body['data']} == set(expected)
        for cat in body['data']:
            assert {row['skuid'] for row in cat['sku']} == expected[cat['catalog_id']]
        page = Client().get('/buyer_dashboard.html')
        assert page.status_code == 200
        html = page.content.decode('utf-8')
        assert 'id="featured-tea-tabs"' in html
        assert 'id="featured-pagination"' in html
        assert 'data-cat="bulk"' not in html and 'data-cat="gift"' not in html
        assert 'data-cat="daily"' not in html and 'data-cat="portable"' not in html
        assert html.index('buyer-catalog-preview.js') < html.index('buyer-workbench.js')
        Path(output).write_text(json.dumps(body, indent=2) + '\n', encoding='utf-8')
        print('PASS: real Django index contract has 2 categories and 30 saleable fixture SKUs; '
              'unlisted/out-of-stock rows excluded; homepage renders HTTP 200 without scenario buttons')
    finally:
        teardown_databases(configuration, verbosity=0)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('Usage: python client/tests/catalog-preview-contract.py <output-json-path>')
    main(sys.argv[1])
