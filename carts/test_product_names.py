"""Cart display identity using an isolated database and an in-memory Redis double."""
import json
from unittest.mock import patch

from django.test import TestCase

from goods.images import sku_image_name
from goods.models import Catalog, SKU, SPU
from tea_saas.utils import jwt_encode
from users.models import UserProfile


class CartProductNameTests(TestCase):
    def setUp(self):
        self.buyer = UserProfile.objects.create(username='cartnames', user_type='customer', is_active=True)
        category = Catalog.objects.create(name='合成茶类')
        self.skus = []
        for product, spec, price in [('合成石牌茶', '默认规格', '75'), ('合成红茶', '礼盒装', '123')]:
            spu = SPU.objects.create(name=product, catalog=category)
            self.skus.append(SKU.objects.create(spu=spu, name=spec, price=price,
                                               market_price=price, cost_price='1', stock=10))
        self.rows = {str(sku.pk): json.dumps({'count': '2', 'status': True})
                     for sku in self.skus}
        self.url = '/v1/carts/' + self.buyer.username
        self.headers = {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': self.buyer.pk})}
        redis = type('MemoryCart', (), {
            'exists': lambda instance, key: True,
            'hgetall': lambda instance, name: self.rows.copy(),
            'hget': lambda instance, name, key: self.rows[str(key)],
        })()
        connection = patch('carts.views.get_redis_connection', return_value=redis)
        connection.start()
        self.addCleanup(connection.stop)
        stock = patch('carts.views.get_available_stock', return_value=10)
        stock.start()
        self.addCleanup(stock.stop)
        cas = patch('carts.atomic_add.compare_set', return_value=True)
        cas.start()
        self.addCleanup(cas.stop)

    def assert_names(self, response, expected):
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['code'], 200)
        self.assertEqual(len(body['data']), len(expected))
        by_id = {str(row['id']): row for row in body['data']}
        for sku in expected:
            row = by_id[str(sku.pk)]
            self.assertEqual(row['product_name'], sku.spu.name)
            self.assertEqual(row['sku_name'], sku.name)
            self.assertEqual(row['name'], sku.name, 'legacy name retains its specification meaning')
            self.assertEqual(row['unit_price'], float(sku.price))
            self.assertEqual(row['price'], float(sku.price) * row['count'])
            self.assertEqual(row['default_image_url'], sku_image_name(sku))

    def test_get_uses_parent_product_without_changing_sku_identity(self):
        self.assert_names(self.client.get(self.url, **self.headers), self.skus)

    def test_quantity_and_selection_responses_keep_product_names(self):
        for state in ('add', 'del', 'select', 'unselect'):
            with self.subTest(state=state):
                response = self.client.put(self.url, data=json.dumps({'state': state, 'sku_id': str(self.skus[0].pk)}),
                                           content_type='application/json', **self.headers)
                self.assert_names(response, self.skus[:1])

    def test_bulk_selection_responses_keep_product_names(self):
        for state in ('selectall', 'unselectall'):
            with self.subTest(state=state):
                response = self.client.put(self.url, data=json.dumps({'state': state}),
                                           content_type='application/json', **self.headers)
                self.assert_names(response, self.skus)
