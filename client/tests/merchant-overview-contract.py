"""Disposable SQLite fixtures verify real merchant metrics and the two-zone template.

python client/tests/merchant-overview-contract.py .scratch/merchant-overview.json
"""
import json
import os
from datetime import timedelta
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
from django.utils import timezone
from goods.models import Catalog, SPU, SKU
from orders.models import OrderInfo, OrderGoods
from tea_saas.utils import jwt_encode
from users.models import UserProfile

def main(output):
    assert settings.DATABASES['default']['ENGINE'] == 'django.db.backends.sqlite3'
    config = setup_databases(verbosity=0, interactive=False, aliases={'default'})
    try:
        buyer = UserProfile.objects.create(username='overview-buyer', is_active=True)
        shop = UserProfile.objects.create(username='overview-shop', user_type='merchant', is_active=True)
        other = UserProfile.objects.create(username='overview-other', user_type='merchant', is_active=True)
        catalog = Catalog.objects.create(name='Fixture tea')
        skus = [SKU.objects.create(spu=SPU.objects.create(name='Synthetic tea', catalog=catalog, merchant=owner),
                                  name='250g', price=10, cost_price=5, market_price=12) for owner in (shop,other)]
        for key, status, amount, sku, old in [('paid',2,100,skus[0],False),('done',4,200,skus[0],False),
                ('unpaid',1,999,skus[0],False),('foreign',2,5000,skus[1],False),('old',2,6000,skus[0],True)]:
            order = OrderInfo.objects.create(order_id='overview-'+key, user_profile=buyer, total_amount=amount,
                total_count=1, freight=0, status=status, receiver='Fixture', address='Fixture', receiver_mobile='000', tag='Fixture')
            OrderGoods.objects.create(order_info=order, sku=sku, count=1, price=amount)
            if old: OrderInfo.objects.filter(pk=order.pk).update(created_time=timezone.now()-timedelta(days=400))
        token = jwt_encode({'id':shop.pk,'username':shop.username})
        if isinstance(token,bytes): token=token.decode()
        client=Client()
        response=client.get('/v1/supplier/analytics?period=year', HTTP_AUTHORIZATION=token)
        assert response.status_code == 200
        body=response.json(); summary=body['data']['summary']
        assert summary['total_sales']==300 and summary['paid_order_count']==2
        assert summary['avg_order_amount']==150 and summary['completion_rate']==33.3
        assert summary['order_count']==3 and summary['completed']==1
        html=client.get('/merchant_dashboard.html').content.decode('utf-8')
        overview=html.split('id="merchant-overview"',1)[1].split('id="merchant-workbench-feed"',1)[0]
        assert overview.count('class="metric-card"')==4
        assert 'nav-panel-link' not in overview and 'data-panel=' not in overview
        assert 'stat-pending-ship' not in html and 'stat-in-transit' not in html
        assert html.count('class="todo-item"')==3 and 'todo-static' not in html
        assert 'OD20240315001' not in html
        assert html.index('merchant-overview.js') < html.index('supplier-workbench.js')
        feed=client.get('/v1/supplier/workbench-feed', HTTP_AUTHORIZATION=token)
        assert feed.status_code==200
        assert feed.json()['data']['todos']['unshipped']==2, 'all-time tasks include the old order'
        assert feed.json()['data']['total']==2, 'unpaid orders do not inflate merchant tasks'
        Path(output).write_text(json.dumps(body),encoding='utf-8')
        print('PASS: real analytics excludes foreign/unpaid/old sales; overview four readonly cards; tasks all-time; no static placeholders')
    finally:
        teardown_databases(config,verbosity=0)

if __name__=='__main__': main(sys.argv[1])
