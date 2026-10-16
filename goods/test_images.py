import base64
import hashlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from dadashop.utils import jwt_encode
from orders.views import build_single_data
from users.models import UserProfile
from .images import resolve_sku_image, sku_image_name
from .models import Catalog, SKU, SKUImage, SPU

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==')


class CatalogImageTests(TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory(prefix='tea-images-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        override = override_settings(MEDIA_ROOT=self.temp.name)
        override.enable()
        self.addCleanup(override.disable)
        self.catalog = Catalog.objects.create(name='红茶', fallback_image='tea_categories/black.png')
        self.write('tea_categories/black.png')
        self.merchant = UserProfile.objects.create(username='tea-shop', user_type='merchant', is_active=True)
        self.spu = SPU.objects.create(name='红茶商品', catalog=self.catalog, merchant=self.merchant)
        self.sku = self.make_sku(self.spu)

    def write(self, name, content=PNG):
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)
        return file

    def make_sku(self, spu, **fields):
        return SKU.objects.create(spu=spu, name='100g', caption='茶', price=10,
                                  cost_price=5, market_price=12, stock=10, **fields)

    def test_virtual_image_served_and_upload_field_remains_empty(self):
        image = resolve_sku_image(self.sku)
        self.assertTrue(image.is_virtual)
        self.assertEqual(image.name, self.catalog.fallback_image.name)
        response = self.client.get(f'/v1/goods/sku/{self.sku.id}/image')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, PNG)
        self.assertEqual(response['X-Image-Source'], 'catalog-virtual')
        self.sku.refresh_from_db()
        self.assertFalse(self.sku.default_image_url)

    def test_real_upload_immediately_overrides_virtual_and_delete_restores_fallback(self):
        encoded = jwt_encode({'id': self.merchant.id})
        if isinstance(encoded, bytes):
            encoded = encoded.decode()
        response = self.client.post(f'/v1/goods/merchant/sku/{self.sku.id}/image',
                                    {'image': SimpleUploadedFile('real.png', PNG, content_type='image/png')},
                                    HTTP_AUTHORIZATION=encoded)
        self.assertEqual(response.json()['code'], 200)
        self.sku.refresh_from_db()
        selected = resolve_sku_image(self.sku)
        self.assertFalse(selected.is_virtual)
        self.assertEqual(selected.name, self.sku.default_image_url.name)
        self.assertEqual(self.client.get(f'/v1/goods/sku/{self.sku.id}/image')['X-Image-Source'], 'product-upload')
        selected.path.unlink()
        self.assertTrue(resolve_sku_image(self.sku).is_virtual)
        self.catalog.refresh_from_db()
        self.assertEqual(self.catalog.fallback_image.name, 'tea_categories/black.png')

    def test_broken_default_and_first_gallery_do_not_hide_valid_gallery(self):
        self.sku.default_image_url = 'sku/missing.png'
        self.sku.save()
        SKUImage.objects.create(sku=self.sku, image='sku/also-missing.png')
        SKUImage.objects.create(sku=self.sku, image='sku/gallery.png')
        self.write('sku/gallery.png')
        self.assertEqual(sku_image_name(self.sku), 'sku/gallery.png')
        self.assertFalse(resolve_sku_image(self.sku).is_virtual)

    def test_real_sibling_and_legacy_photos_take_priority(self):
        other = self.make_sku(self.spu, default_image_url='sku/sibling.png')
        self.write('sku/sibling.png')
        self.assertEqual(sku_image_name(self.sku), 'sku/sibling.png')
        self.write(f'sku/{self.sku.id}/own.png')
        self.assertEqual(sku_image_name(self.sku), f'sku/{self.sku.id}/own.png')

    def test_catalogs_are_isolated_and_missing_files_use_generic_placeholder(self):
        green = Catalog.objects.create(name='绿茶', fallback_image='tea_categories/green.png')
        self.write('tea_categories/green.png')
        other = self.make_sku(SPU.objects.create(name='绿茶商品', catalog=green))
        self.assertEqual(sku_image_name(other), 'tea_categories/green.png')
        (self.root / green.fallback_image.name).unlink()
        self.assertIsNone(resolve_sku_image(other))
        self.assertEqual(self.client.get(f'/v1/goods/sku/{other.id}/image').status_code, 200)
        self.assertEqual(self.client.get('/v1/goods/sku/999999/image').status_code, 404)

    def test_storefront_and_order_dtos_use_resolved_paths(self):
        index = self.client.get('/v1/goods/index').json()
        self.assertEqual(index['data'][0]['sku'][0]['image'], 'tea_categories/black.png')
        page = self.client.get(f'/v1/goods/catalogs/{self.catalog.id}').json()
        self.assertEqual(page['data'][0]['image'], 'tea_categories/black.png')
        detail = self.client.get(f'/v1/goods/detail/{self.sku.id}').json()
        self.assertEqual(detail['data']['image'], 'tea_categories/black.png')
        self.assertTrue(detail['data']['image_base64'].startswith('data:image/png;base64,'))
        self.assertEqual(build_single_data(self.sku, 1, True)['default_image_url'], 'tea_categories/black.png')

    def test_cart_uses_fallback_with_fake_redis(self):
        buyer = UserProfile.objects.create(username='image-buyer', is_active=True)
        redis = Mock()
        redis.hgetall.return_value = {str(self.sku.id).encode(): json.dumps({'count': '1', 'status': True}).encode()}
        with patch('carts.views.get_redis_connection', return_value=redis):
            response = self.client.get('/v1/carts/' + buyer.username)
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(response.json()['data'][0]['default_image_url'], 'tea_categories/black.png')

    def test_registration_previews_applies_idempotently_and_validates_hash(self):
        self.catalog.fallback_image = ''
        self.catalog.save()
        manifest = self.root / 'manifest.json'
        payload = {'entries': [{'name': '红茶', 'file': 'tea_categories/black.png',
                                'sha256': hashlib.sha256(PNG).hexdigest()}]}
        manifest.write_text(json.dumps(payload), encoding='utf-8')
        output = io.StringIO()
        call_command('register_tea_images', manifest=str(manifest), stdout=output)
        self.catalog.refresh_from_db()
        self.assertFalse(self.catalog.fallback_image)
        for _ in range(2):
            call_command('register_tea_images', manifest=str(manifest), apply=True, stdout=output)
        self.catalog.refresh_from_db()
        self.assertEqual(self.catalog.fallback_image.name, 'tea_categories/black.png')
        payload['entries'][0]['sha256'] = 'bad'
        manifest.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaises(CommandError):
            call_command('register_tea_images', manifest=str(manifest), apply=True, stdout=output)
