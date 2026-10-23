"""Sales-first recommendations use all merchants and preserve catalog stock semantics."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from goods.models import Catalog, SKU, SPU
from inventory.models import Inventory, Warehouse
from users.models import UserProfile


class SalesRecommendationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Catalog.objects.create(name='红茶')
        cls.spus = []
        for number in range(2):
            merchant = UserProfile.objects.create(username='sales-shop-' + str(number), user_type='merchant', is_active=True)
            cls.spus.append(SPU.objects.create(name='Synthetic tea ' + str(number), catalog=category, merchant=merchant))

    def sku(self, merchant=0, **values):
        options = dict(spu=self.spus[merchant], name='Synthetic specification', caption='', price=10,
                       cost_price=5, market_price=12, stock=10, sales=0, is_launched=True, is_recommended=False)
        options.update(values)
        return SKU.objects.create(**options)

    def recommendations(self):
        response = self.client.get('/v1/goods/recommended-products')
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['code'], 200)
        self.assertIn('base_url', body)
        return body['data']

    def test_all_merchants_compete_by_sales_without_manual_flag_priority(self):
        flagged = self.sku(sales=2, is_recommended=True)
        highest = self.sku(merchant=1, sales=500)
        middle = self.sku(sales=100)
        rows = self.recommendations()
        self.assertEqual([row['skuid'] for row in rows], [highest.pk, middle.pk, flagged.pk])
        self.assertTrue({'price', 'product_name', 'image', 'image_url', 'link'} <= set(rows[0]))

    def test_unlisted_and_sold_out_skus_never_occupy_slots(self):
        self.sku(sales=1000, is_launched=False)
        self.sku(sales=900, stock=0, is_recommended=True)
        self.sku(sales=800, stock=-1)
        eligible = self.sku(sales=1)
        self.assertEqual([row['skuid'] for row in self.recommendations()], [eligible.pk])

    def test_more_than_eighty_sold_out_products_do_not_hide_available_skus(self):
        for number in range(85):
            self.sku(sales=1000 + number, stock=0)
        eligible = self.sku(sales=1)
        self.assertEqual([row['skuid'] for row in self.recommendations()], [eligible.pk])

    def test_sales_ties_use_updated_time_then_id_descending(self):
        older = self.sku(sales=10)
        newer = self.sku(sales=10)
        newest_id = self.sku(sales=10)
        now = timezone.now()
        SKU.objects.filter(pk=older.pk).update(updated_time=now - timedelta(days=1))
        SKU.objects.filter(pk__in=[newer.pk, newest_id.pk]).update(updated_time=now)
        self.assertEqual([row['skuid'] for row in self.recommendations()], [newest_id.pk, newer.pk, older.pk])

    def test_ledger_is_authoritative_and_legacy_fallback_requires_no_ledger(self):
        ledger_only = self.sku(sales=30, stock=0)
        legacy_only = self.sku(sales=20, stock=5)
        unavailable = self.sku(sales=100, stock=0)
        no_ledger = self.sku(sales=10, stock=5)
        for number, available in enumerate((3, 4)):
            warehouse = Warehouse.objects.create(name='Synthetic warehouse', code='sales-' + str(number), address='synthetic')
            Inventory.objects.create(sku=ledger_only, warehouse=warehouse, quantity=available, available_quantity=available)
            Inventory.objects.create(sku=legacy_only, warehouse=warehouse, quantity=0, available_quantity=0)
            Inventory.objects.create(sku=unavailable, warehouse=warehouse, quantity=5, reserved_quantity=5)
        self.assertEqual([row['skuid'] for row in self.recommendations()], [ledger_only.pk, no_ledger.pk])

    def test_returns_top_twenty_with_no_duplicate_skus(self):
        skus = [self.sku(merchant=number % 2, sales=number) for number in range(25)]
        rows = self.recommendations()
        self.assertEqual([row['skuid'] for row in rows], [sku.pk for sku in reversed(skus[5:])])

    def test_no_eligible_products_returns_empty_list(self):
        self.sku(stock=0)
        self.assertEqual(self.recommendations(), [])
