"""Merchant order UI contract against isolated SQLite; no business DB or real tokens."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['DJANGO_SETTINGS_MODULE'] = 'support_ai.test_settings'
import django
django.setup()
from django.conf import settings
from django.contrib.staticfiles import finders
from django.test import Client
from django.test.utils import setup_databases, teardown_databases
from goods.models import Catalog, SPU, SKU
from orders.models import OrderInfo, OrderGoods, TrialOrder, PreSaleOrder
from users.models import UserProfile


def main():
    assert settings.DATABASES['default']['NAME'] == ':memory:'
    databases = setup_databases(verbosity=0, interactive=False, aliases={'default'})
    try:
        merchant = UserProfile.objects.create(username='fixture-merchant', user_type='merchant')
        other = UserProfile.objects.create(username='fixture-other', user_type='merchant')
        buyer = UserProfile.objects.create(username='fixture-buyer', user_type='customer')
        catalog = Catalog.objects.create(name='Fixture')
        def sku_for(owner):
            spu = SPU.objects.create(name='Fixture tea', catalog=catalog, merchant=owner)
            return SKU.objects.create(spu=spu, name='Fixture spec', price=35, cost_price=1,
                                      market_price=35, stock=100, is_launched=True)
        sku, foreign_sku = sku_for(merchant), sku_for(other)
        def make_order(order_id, status, item=sku, kind='standard'):
            order = OrderInfo.objects.create(order_id=order_id, user_profile=buyer, order_type=kind,
                total_amount=35, total_count=1, freight=0, status=status,
                receiver='Fixture', receiver_mobile='13000000000', address='Fixture address', tag='test')
            OrderGoods.objects.create(order_info=order, sku=item, count=1, price=35)
            return order
        for number in range(13):
            make_order(str(number), min(number + 1, 4) if number < 4 else 1)
        TrialOrder.objects.create(order_info=make_order('trial', 4, kind='trial'), status=4)
        PreSaleOrder.objects.create(order_info=make_order('presale', 1, kind='presale'), status=3,
                                    deposit_amount=5, balance_amount=30)
        make_order('foreign', 1, foreign_sku)
        client = Client()
        assert client.get('/v1/supplier/orders').status_code == 401
        with patch('users.decorators.jwt_decode', return_value={'id': buyer.pk}):
            assert client.get('/v1/supplier/orders', HTTP_AUTHORIZATION='fixture').status_code == 403
        with patch('users.decorators.jwt_decode', return_value={'id': merchant.pk}):
            def orders():
                result = client.get('/v1/supplier/orders', HTTP_AUTHORIZATION='fixture')
                assert result.status_code == 200
                return result.json()
            body = orders()
            assert len(body['data']) == 15
            assert 'foreign' not in {row['order_id'] for row in body['data']}
            assert all({'status', 'status_text', 'order_id', 'total_amount', 'address'} <= row.keys() for row in body['data'])
            # Pass the real response directly to the frontend behavior tests without writing personal data.
            subprocess.run(['node', str(ROOT / 'client/tests/merchant-orders.test.js'), '-'],
                           input=json.dumps(body), encoding='utf-8', check=True)
            assert client.post('/v1/supplier/orders/1/ship', HTTP_AUTHORIZATION='fixture').json()['code'] == 200
            refreshed = next(row for row in orders()['data'] if row['order_id'] == '1')
            assert refreshed['status'] == 3
            assert client.post('/v1/supplier/orders/delete', data=json.dumps({'order_id': '0'}),
                               content_type='application/json', HTTP_AUTHORIZATION='fixture').json()['code'] == 200
            assert len(orders()['data']) == 14
        page = client.get('/merchant_orders.html?embed=1&filter=unshipped')
        assert page.status_code == 200
        html = page.content.decode()
        assert 'id="order-status-filters"' in html and 'aria-live="polite"' in html
        assert html.index('system-theme.css') < html.index('merchant-orders.css')
        for kind in ('js', 'css'):
            assert finders.find(f'{kind}/merchant-orders.{kind}')
        css = (ROOT / 'client/static/css/merchant-orders.css').read_text(encoding='utf-8')
        assert 'overflow-x: auto' in css and 'min-width: 1180px' in css and 'white-space: nowrap' in css
        print('PASS: isolated merchant scope, 15 orders, subtype fields, API ship/delete refresh, rendered template and static assets')
    finally:
        teardown_databases(databases, verbosity=0)


if __name__ == '__main__':
    main()
