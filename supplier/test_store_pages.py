"""Store publication and object boundaries; fixtures only, never the business database."""
import copy
import json
import tempfile
from io import BytesIO

from PIL import Image
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from goods.models import Catalog, SKU, SPU
from tea_saas.utils import jwt_encode
from users.models import Role, UserProfile, UserRole
from .models import StorePage


class StorePageTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.merchant = UserProfile.objects.create(username='store_a', user_type='merchant',
            is_active=True, shop_name='甲茶园', shop_description='原始介绍')
        cls.other = UserProfile.objects.create(username='store_b', user_type='merchant', is_active=True, shop_name='乙茶园')
        cls.buyer = UserProfile.objects.create(username='buyer_s', is_active=True)
        cls.catalog = Catalog.objects.create(name='红茶')
        cls.skus = []
        for merchant in (cls.merchant, cls.other):
            spu = SPU.objects.create(name=merchant.shop_name + '红茶', merchant=merchant, catalog=cls.catalog)
            cls.skus.append(SKU.objects.create(name='150g', spu=spu, price=12, market_price=14,
                cost_price=8, stock=10, is_launched=True))

    def auth(self, user=None):
        return {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': (user or self.merchant).pk})}

    def content(self, **changes):
        data = {'name': '甲茶园', 'summary': '认真做好一杯茶', 'welcome': '欢迎来茶园',
                'story': '茶园故事\n产地介绍', 'logo_url': '', 'banner_url': '', 'featured_ids': [self.skus[0].pk]}
        data.update(changes)
        return data

    def write(self, method='put', user=None, **data):
        return getattr(self.client, method)('/v1/supplier/store-page', json.dumps(data),
                                           content_type='application/json', **self.auth(user))

    def publish(self, merchant=None, content=None):
        merchant = merchant or self.merchant
        content = content if content is not None else self.content()
        page = StorePage.objects.create(merchant=merchant, draft=content, published=copy.deepcopy(content),
                                       is_published=True, revision=1)
        return page

    def test_initial_get_has_no_write_and_uses_existing_shop_data(self):
        response = self.client.get('/v1/supplier/store-page', **self.auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['draft']['name'], '甲茶园')
        self.assertFalse(StorePage.objects.exists())
        self.assertIn('no-store', response['Cache-Control'])

    def test_anonymous_buyer_and_inactive_cannot_manage(self):
        self.assertEqual(self.client.get('/v1/supplier/store-page').status_code, 401)
        self.assertEqual(self.client.get('/v1/supplier/store-page', **self.auth(self.buyer)).status_code, 403)
        self.merchant.is_active = False
        self.merchant.save()
        self.assertEqual(self.client.get('/v1/supplier/store-page', **self.auth()).status_code, 403)

    def test_supplier_role_is_supported(self):
        role, _ = Role.objects.get_or_create(code='supplier', defaults={'name': '供应商'})
        UserRole.objects.create(user_profile=self.buyer, role=role)
        self.assertEqual(self.client.get('/v1/supplier/store-page', **self.auth(self.buyer)).status_code, 200)

    def test_draft_is_private_until_explicit_publish(self):
        response = self.write(revision=0, content=self.content())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['data']['revision'], 1)
        self.assertEqual(self.client.get(f'/v1/stores/{self.merchant.pk}').status_code, 404)
        self.assertEqual(self.client.get(f'/v1/stores/{self.merchant.pk}/products').status_code, 404)
        response = self.write('post', revision=1, action='publish')
        self.assertEqual(response.status_code, 200)
        data = self.client.get(f'/v1/stores/{self.merchant.pk}').json()['data']
        self.assertEqual(data['content']['story'], '茶园故事\n产地介绍')
        self.assertNotIn('draft', data)
        self.assertNotIn('username', json.dumps(data))
        self.assertNotIn('email', json.dumps(data))

    def test_saved_edits_do_not_change_published_snapshot_or_card_name(self):
        self.publish()
        self.assertEqual(self.write(revision=1, content=self.content(name='未发布店名')).status_code, 200)
        response = self.client.get(f'/v1/stores/{self.merchant.pk}')
        self.assertEqual(response.json()['data']['content']['name'], '甲茶园')
        rows = self.client.get('/v1/goods/index').json()['data'][0]['sku']
        row = next(row for row in rows if row['skuid'] == self.skus[0].pk)
        self.assertEqual(row['merchant']['name'], '甲茶园')
        self.assertNotIn('未发布店名', response.content.decode())

    def test_publish_updates_existing_shop_identity(self):
        self.write(revision=0, content=self.content(name='新店名'))
        self.write('post', revision=1, action='publish')
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.shop_name, '新店名')

    def test_other_merchant_cannot_read_or_overwrite_owner_draft(self):
        self.publish()
        response = self.client.get('/v1/supplier/store-page?merchant_id=' + str(self.merchant.pk), **self.auth(self.other))
        self.assertEqual(response.json()['data']['merchant_id'], self.other.pk)
        self.assertEqual(self.write(user=self.other, revision=0, merchant_id=self.merchant.pk,
                                    content=self.content()).status_code, 400)
        self.assertEqual(StorePage.objects.get(merchant=self.merchant).revision, 1)

    def test_foreign_recommendation_and_asset_are_rejected(self):
        self.assertEqual(self.write(revision=0, content=self.content(featured_ids=[self.skus[1].pk])).status_code, 400)
        self.assertEqual(self.write(revision=0, content=self.content(
            logo_url=f'/media/store-pages/{self.other.pk}/logo.webp')).status_code, 400)

    def test_conflict_keeps_newer_saved_content(self):
        self.publish()
        self.assertEqual(self.write(revision=1, content=self.content(name='较新版本')).status_code, 200)
        self.assertEqual(self.write(revision=1, content=self.content(name='旧页面覆盖')).status_code, 409)
        self.assertEqual(self.write('post', revision=1, action='publish').status_code, 409)
        self.assertEqual(StorePage.objects.get(merchant=self.merchant).draft['name'], '较新版本')

    def test_validation_rejects_bad_payloads(self):
        for data in (self.content(name='a' * 51), self.content(summary=3), self.content(featured_ids=[True]),
                     self.content(featured_ids=[self.skus[0].pk] * 2), self.content(logo_url='javascript:alert(1)'),
                     self.content(banner_url='https://example.org/banner.jpg')):
            with self.subTest(data=data):
                self.assertEqual(self.write(revision=0, content=data).status_code, 400)
        self.assertEqual(self.client.put('/v1/supplier/store-page', '{broken',
            content_type='application/json', **self.auth()).status_code, 400)
        self.assertEqual(self.write(revision=True, content=self.content()).status_code, 400)
        self.assertEqual(self.write('post', revision=0, action='delete').status_code, 400)
        self.assertEqual(self.write('post', revision=0, action='publish', content=self.content()).status_code, 400)

    def test_missing_name_cannot_publish(self):
        self.write(revision=0, content=self.content(name=''))
        self.assertEqual(self.write('post', revision=1, action='publish').status_code, 400)
        self.assertFalse(StorePage.objects.get(merchant=self.merchant).is_published)

    def test_unpublish_only_closes_homepage_not_goods(self):
        self.publish()
        self.assertEqual(self.write('post', revision=1, action='unpublish').status_code, 200)
        self.assertEqual(self.client.get(f'/v1/stores/{self.merchant.pk}').status_code, 404)
        self.skus[0].refresh_from_db()
        self.assertTrue(self.skus[0].is_launched)
        rows = self.client.get('/v1/goods/index').json()['data'][0]['sku']
        self.assertIn(self.skus[0].pk, [row['skuid'] for row in rows])
        row = next(row for row in rows if row['skuid'] == self.skus[0].pk)
        self.assertIsNone(row['merchant']['url'])

    def test_public_products_are_only_current_store_and_live_stock(self):
        self.publish()
        response = self.client.get(f'/v1/stores/{self.merchant.pk}/products')
        self.assertEqual([row['skuid'] for row in response.json()['data']], [self.skus[0].pk])
        self.skus[0].stock = 0
        self.skus[0].save()
        response = self.client.get(f'/v1/stores/{self.merchant.pk}')
        self.assertEqual(response.json()['data']['featured'], [])
        self.assertEqual(response.json()['data']['product_count'], 0)

    def test_unlaunched_or_deleted_recommendations_disappear_live(self):
        self.publish()
        self.skus[0].is_launched = False
        self.skus[0].save()
        self.assertEqual(self.client.get(f'/v1/stores/{self.merchant.pk}').json()['data']['featured'], [])
        self.skus[0].delete()
        self.assertEqual(self.client.get(f'/v1/stores/{self.merchant.pk}').json()['data']['featured'], [])
        self.assertEqual(self.write('post', revision=1, action='publish').status_code, 400)

    def test_inactive_or_demoted_merchant_is_not_public(self):
        self.publish()
        self.merchant.is_active = False
        self.merchant.save()
        self.assertEqual(self.client.get(f'/v1/stores/{self.merchant.pk}').status_code, 404)
        self.merchant.is_active = True
        self.merchant.user_type = 'customer'
        self.merchant.save()
        self.assertEqual(self.client.get(f'/v1/stores/{self.merchant.pk}/products').status_code, 404)
        rows = self.client.get('/v1/goods/index').json()['data'][0]['sku']
        self.assertIsNone(next(row for row in rows if row['skuid'] == self.skus[0].pk)['merchant']['url'])

    def test_store_search_category_sort_and_pagination(self):
        self.publish()
        for n in range(13):
            SKU.objects.create(name='本店新茶' + str(n), spu=self.skus[0].spu, price=n + 20,
                               cost_price=1, market_price=50, stock=2, is_launched=True)
        url = f'/v1/stores/{self.merchant.pk}/products'
        first = self.client.get(url + '?sort=price_asc').json()
        second = self.client.get(url + '?sort=price_asc&page=2').json()
        self.assertEqual(first['pagination']['total'], 14)
        ids = [row['skuid'] for row in first['data'] + second['data']]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(second['data']), 4)
        self.assertEqual(self.client.get(url + '?q=本店新茶').json()['pagination']['total'], 13)
        self.assertEqual(self.client.get(url + '?q=乙茶园').json()['data'], [])
        self.assertEqual(self.client.get(url + '?catalog_id=999').json()['data'], [])
        self.assertEqual(self.client.get(url + '?sort=invalid').status_code, 400)
        self.assertEqual(self.client.get(url + '?catalog_id=bad').status_code, 400)

    def test_platform_keeps_multiple_merchants_and_detail_has_store_link(self):
        self.publish()
        self.publish(self.other, self.content(name='乙茶园', featured_ids=[self.skus[1].pk]))
        rows = self.client.get('/v1/goods/index').json()['data'][0]['sku']
        self.assertEqual({row['merchant']['id'] for row in rows}, {self.merchant.pk, self.other.pk})
        self.assertEqual(self.client.get(f'/v1/goods/detail/{self.skus[0].pk}').json()['data']['merchant']['url'],
                         f'/store.html?merchant_id={self.merchant.pk}')
        recommended = self.client.get('/v1/goods/recommended-products')
        self.assertEqual(recommended.status_code, 200)
        self.assertEqual({row['merchant']['id'] for row in recommended.json()['data']},
                         {self.merchant.pk, self.other.pk})

    def test_unassigned_historical_product_has_no_invented_store(self):
        self.skus[0].spu.merchant = None
        self.skus[0].spu.save()
        rows = self.client.get('/v1/goods/index').json()['data'][0]['sku']
        self.assertIsNone(next(row for row in rows if row['skuid'] == self.skus[0].pk)['merchant'])

    def test_public_endpoints_are_read_only(self):
        self.publish()
        self.assertEqual(self.client.post(f'/v1/stores/{self.merchant.pk}', {}).status_code, 405)
        self.assertEqual(self.client.post(f'/v1/stores/{self.merchant.pk}/products', {}).status_code, 405)
        self.assertEqual(self.client.delete('/v1/supplier/store-page', **self.auth()).status_code, 405)

    def test_upload_auth_validation_and_reencoding(self):
        url = '/v1/supplier/store-page/image'
        self.assertEqual(self.client.post(url).status_code, 401)
        self.assertEqual(self.client.post(url, **self.auth(self.buyer)).status_code, 403)
        with tempfile.TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            buffer = BytesIO()
            Image.new('RGB', (80, 40), 'green').save(buffer, 'PNG')
            response = self.client.post(url, {'kind': 'logo', 'image': SimpleUploadedFile('logo.png', buffer.getvalue())}, **self.auth())
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.json()['data']['url'].startswith(f'/media/store-pages/{self.merchant.pk}/'))
            self.assertTrue(response.json()['data']['url'].endswith('.webp'))
            self.assertEqual(self.client.post(url, {'kind': 'banner', 'image': SimpleUploadedFile('x.svg', b'<svg/>')}, **self.auth()).status_code, 400)

    def test_pages_render_with_entry_and_disabled_preview_actions(self):
        self.assertContains(self.client.get('/merchant_dashboard.html'), 'data-panel="merchant_store.html"')
        self.assertContains(self.client.get('/merchant_store.html?embed=1'), '店铺页面管理')
        self.assertContains(self.client.get('/store.html?merchant_id=1'), '本店全部商品')
        self.assertContains(self.client.get('/buyer_dashboard.html'), '/static/js/storefront.js')
