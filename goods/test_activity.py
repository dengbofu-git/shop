from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.db import IntegrityError, connections, transaction
from django.test import Client, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone

from dadashop.utils import jwt_encode
from users.models import UserProfile
from .models import BrowsingHistory, Catalog, Favorite, SKU, SPU


class BuyerActivityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = UserProfile.objects.create(username='buyer', is_active=True)
        cls.other = UserProfile.objects.create(username='other', is_active=True)
        cls.merchant = UserProfile.objects.create(username='merchant', user_type='merchant', is_active=True)
        cls.inactive = UserProfile.objects.create(username='inactive', is_active=False)
        catalog = Catalog.objects.create(name='红茶')
        cls.spu = SPU.objects.create(name='测试茶品', catalog=catalog)
        cls.skus = [SKU.objects.create(
            spu=cls.spu, name=f'规格 {i}', caption='测试', price='38.50',
            cost_price='20', market_price='50', stock=10,
        ) for i in range(14)]

    def call(self, method, path, user=None, **kwargs):
        encoded = jwt_encode({'id': (user or self.buyer).id})
        if isinstance(encoded, bytes):
            encoded = encoded.decode()
        return getattr(self.client, method)(
            '/v1/goods/' + path, HTTP_AUTHORIZATION='Bearer ' + encoded, **kwargs
        )

    def test_all_endpoints_require_valid_active_buyer(self):
        for method, path in [('get', 'favorites'), ('get', 'favorites/1'),
                             ('put', 'favorites/1'), ('delete', 'favorites/1'),
                             ('get', 'recent'), ('delete', 'recent'),
                             ('post', 'recent/1'), ('delete', 'recent/1')]:
            with self.subTest(method=method, path=path):
                url = '/v1/goods/' + path
                self.assertEqual(getattr(self.client, method)(url).status_code, 401)
                self.assertEqual(getattr(self.client, method)(url, HTTP_AUTHORIZATION='bad-token').status_code, 401)
                self.assertEqual(self.call(method, path, self.merchant).status_code, 403)
                self.assertEqual(self.call(method, path, self.inactive).status_code, 401)

    def test_favorite_idempotency_state_and_uniqueness(self):
        path = f'favorites/{self.skus[0].id}'
        self.assertFalse(self.call('get', path).json()['data']['is_favorite'])
        self.call('put', path)
        row = Favorite.objects.get(user=self.buyer)
        self.call('put', path)
        self.assertEqual(Favorite.objects.filter(user=self.buyer).count(), 1)
        self.assertEqual(Favorite.objects.get(pk=row.pk).created_time, row.created_time)
        self.assertTrue(self.call('get', path).json()['data']['is_favorite'])
        with self.assertRaises(IntegrityError), transaction.atomic():
            Favorite.objects.create(user=self.buyer, sku=self.skus[0])
        self.assertEqual(self.call('delete', path).status_code, 200)
        self.assertEqual(self.call('delete', path).status_code, 200)
        self.assertFalse(self.call('get', path).json()['data']['is_favorite'])

    def test_cross_account_read_delete_and_clear_are_isolated(self):
        sku = self.skus[0]
        Favorite.objects.create(user=self.other, sku=sku)
        BrowsingHistory.objects.create(user=self.other, sku=sku)
        # Spoofed owner fields and query params must never determine the account.
        self.call('put', f'favorites/{sku.id}', data='{"user_id": %d}' % self.other.id, content_type='application/json')
        self.assertEqual(self.call('get', f'recent?user_id={self.other.id}').json()['data'], [])
        self.call('delete', f'favorites/{sku.id}')
        self.call('delete', f'recent/{sku.id}')
        self.call('delete', 'recent')
        self.assertEqual(Favorite.objects.filter(user=self.other).count(), 1)
        self.assertEqual(BrowsingHistory.objects.filter(user=self.other).count(), 1)
        self.assertEqual(self.call('get', 'favorites').json()['data'], [])

    def test_recent_deduplicates_and_revisit_moves_to_front(self):
        for sku in self.skus[:2]:
            self.call('post', f'recent/{sku.id}')
        BrowsingHistory.objects.filter(sku=self.skus[0]).update(viewed_time=timezone.now() - timedelta(days=1))
        self.call('post', f'recent/{self.skus[0].id}')
        data = self.call('get', 'recent').json()['data']
        self.assertEqual([r['skuid'] for r in data], [self.skus[0].id, self.skus[1].id])
        self.assertEqual(BrowsingHistory.objects.count(), 2)
        with self.assertRaises(IntegrityError), transaction.atomic():
            BrowsingHistory.objects.create(user=self.buyer, sku=self.skus[0])

    def test_history_retention_removal_and_clear_leave_favorites(self):
        extra = [SKU.objects.create(spu=self.spu, name=str(i), caption='', price=1,
                                   cost_price=1, market_price=1) for i in range(101)]
        old = timezone.now() - timedelta(days=2)
        for sku in extra[:100]:
            BrowsingHistory.objects.create(user=self.buyer, sku=sku)
        BrowsingHistory.objects.filter(sku=extra[0]).update(viewed_time=old)
        self.call('post', f'recent/{extra[100].id}')
        self.assertEqual(BrowsingHistory.objects.count(), 100)
        self.assertFalse(BrowsingHistory.objects.filter(sku=extra[0]).exists())
        Favorite.objects.create(user=self.buyer, sku=extra[100])
        self.call('delete', f'recent/{extra[100].id}')
        self.call('delete', f'recent/{extra[100].id}')
        self.assertEqual(BrowsingHistory.objects.count(), 99)
        self.call('delete', 'recent')
        self.assertFalse(BrowsingHistory.objects.exists())
        self.assertEqual(Favorite.objects.count(), 1)

    def test_pagination_current_product_fields_and_favorite_projection(self):
        for sku in self.skus:
            Favorite.objects.create(user=self.buyer, sku=sku)
            BrowsingHistory.objects.create(user=self.buyer, sku=sku)
        SKU.objects.filter(pk=self.skus[-1].pk).update(price='42.00')
        for endpoint in ['favorites', 'recent']:
            first = self.call('get', endpoint)
            self.assertEqual(first['Cache-Control'], 'no-store')
            data = first.json()
            self.assertEqual(data['paginator'], {'page': 1, 'pages': 2, 'pagesize': 12, 'total': 14})
            self.assertEqual(len(data['data']), 12)
            self.assertEqual(data['data'][0]['price'], '42.00')
            self.assertTrue(data['data'][0]['is_favorite'])
            self.assertEqual(data['data'][0]['product_name'], '测试茶品')
            self.assertEqual(len(self.call('get', endpoint + '?page=2').json()['data']), 2)
            self.assertEqual(self.call('get', endpoint + '?page=999').json()['paginator']['page'], 2)
            for value in ['0', '-1', 'bad', '1.5']:
                self.assertEqual(self.call('get', endpoint + '?page=' + value).status_code, 400)

    def test_unlaunched_and_missing_products(self):
        sku = self.skus[0]
        self.call('put', f'favorites/{sku.id}')
        self.call('post', f'recent/{sku.id}')
        SKU.objects.filter(pk=sku.pk).update(is_launched=False)
        for endpoint in ['favorites', 'recent']:
            self.assertFalse(self.call('get', endpoint).json()['data'][0]['is_launched'])
        for sku_id in [sku.id, 999999]:
            self.assertEqual(self.call('put', f'favorites/{sku_id}').status_code, 404)
            self.assertEqual(self.call('post', f'recent/{sku_id}').status_code, 404)
            self.assertEqual(self.call('delete', f'favorites/{sku_id}').status_code, 200)
            self.assertEqual(self.call('delete', f'recent/{sku_id}').status_code, 200)

    def test_deleted_sku_cascades_records(self):
        sku = self.skus[0]
        Favorite.objects.create(user=self.buyer, sku=sku)
        BrowsingHistory.objects.create(user=self.buyer, sku=sku)
        sku.delete()
        self.assertEqual(self.call('get', 'favorites').json()['data'], [])
        self.assertEqual(self.call('get', 'recent').json()['data'], [])

    def test_wrong_methods_do_not_write(self):
        for method, path in [('post', 'favorites'), ('post', 'favorites/1'),
                             ('put', 'recent'), ('get', 'recent/1')]:
            response = self.call(method, path)
            self.assertEqual(response.status_code, 405)
            self.assertIn('Allow', response)
        self.assertFalse(BrowsingHistory.objects.exists())
        self.assertFalse(Favorite.objects.exists())

    def test_page_routes_and_header_links(self):
        for page in ['myCollect.html', 'recent.html']:
            response = self.client.get('/' + page)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'id="activity-grid"')
            self.assertContains(response, 'href="recent.html"')
            self.assertNotContains(response, 'class="activity-tabs"')
        detail = self.client.get('/product_details.html')
        self.assertContains(detail, 'id="favorite-toggle"')


@skipUnlessDBFeature('has_select_for_update')
class BuyerActivityConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.user = UserProfile.objects.create(username='parallel', is_active=True)
        catalog = Catalog.objects.create(name='红茶')
        spu = SPU.objects.create(name='并发测试', catalog=catalog)
        self.skus = [SKU.objects.create(spu=spu, name=str(i), caption='', price=1,
                                       cost_price=1, market_price=1) for i in range(101)]
        encoded = jwt_encode({'id': self.user.id})
        self.authorization = encoded.decode() if isinstance(encoded, bytes) else encoded

    def parallel(self, method, paths):
        barrier = Barrier(len(paths))

        def call(path):
            try:
                barrier.wait(timeout=10)
                return getattr(Client(), method)('/v1/goods/' + path,
                                                  HTTP_AUTHORIZATION=self.authorization).status_code
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(paths)) as pool:
            return list(pool.map(call, paths))

    def test_concurrent_history_writes_keep_latest_100(self):
        for sku in self.skus[:99]:
            BrowsingHistory.objects.create(user=self.user, sku=sku)
        result = self.parallel('post', [f'recent/{sku.id}' for sku in self.skus[99:]])
        self.assertEqual(result, [200, 200])
        self.assertEqual(BrowsingHistory.objects.filter(user=self.user).count(), 100)
        self.assertEqual(BrowsingHistory.objects.filter(user=self.user, sku__in=self.skus[99:]).count(), 2)

    def test_concurrent_favorite_requests_create_one_record(self):
        path = f'favorites/{self.skus[0].id}'
        self.assertEqual(self.parallel('put', [path, path]), [200, 200])
        self.assertEqual(Favorite.objects.filter(user=self.user).count(), 1)
