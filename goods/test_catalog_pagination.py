from django.test import TestCase

from goods.models import Catalog, SKU, SPU


class CatalogPaginationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.catalog = Catalog.objects.create(name='Pagination fixture')
        spu = SPU.objects.create(name='Fixture tea', catalog=cls.catalog)
        cls.ids = []
        for index in range(23):
            sku = SKU.objects.create(
                spu=spu, name='Spec ' + str(index), price=10,
                cost_price=5, market_price=12, stock=10, is_launched=True,
            )
            cls.ids.append(sku.pk)
        SKU.objects.create(spu=spu, name='Unlisted', price=10, cost_price=5,
                           market_price=12, stock=10, is_launched=False)
        SKU.objects.create(spu=spu, name='No stock', price=10, cost_price=5,
                           market_price=12, stock=0, is_launched=True)

    def get_page(self, **params):
        response = self.client.get('/v1/goods/catalogs/' + str(self.catalog.pk), params)
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_ten_items_per_page_without_omissions_or_duplicates(self):
        found = []
        for page, count in [(1, 10), (2, 10), (3, 3)]:
            body = self.get_page(page=page, page_size=10)
            self.assertEqual(body['paginator'], {'pagesize': 10, 'total': 23})
            self.assertEqual(len(body['data']), count)
            found.extend(row['skuid'] for row in body['data'])
        self.assertEqual(found, sorted(self.ids, reverse=True))

    def test_existing_default_and_invalid_page_sizes(self):
        self.assertEqual(len(self.get_page()['data']), 12)
        for invalid in ['bad', '', '0', '-1', '101']:
            with self.subTest(page_size=invalid):
                self.assertEqual(self.get_page(page_size=invalid)['paginator']['pagesize'], 12)

    def test_empty_category_stays_empty(self):
        empty = Catalog.objects.create(name='Empty fixture')
        response = self.client.get('/v1/goods/catalogs/' + str(empty.pk), {'page_size': 10})
        self.assertEqual(response.json()['data'], [])
        self.assertEqual(response.json()['paginator'], {'pagesize': 10, 'total': 0})
