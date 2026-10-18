import io
import json
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection, OperationalError
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from goods.models import Catalog, SPU, SKU, ProductAttribute, ProductAttributeValue
from inventory.models import Inventory, Warehouse
from .product_details import get_product_details


class PublicProductDetailsTests(TestCase):
    def setUp(self):
        self.spu = SPU.objects.create(name='测试绿茶', catalog=Catalog.objects.create(name='绿茶'))
        self.sku = SKU.objects.create(name='50克装', caption='', spu=self.spu, price='12.30',
                                      cost_price='3.21', market_price='15', stock=10)

    def test_public_shape_legacy_stock_and_read_only_queries(self):
        with CaptureQueriesContext(connection) as queries:
            result = get_product_details(self.sku.pk)
        self.assertTrue(queries)
        self.assertTrue(all(q['sql'].lstrip().upper().startswith('SELECT') for q in queries))
        self.assertFalse(any('cost_price' in q['sql'] or 'merchant_id' in q['sql'] for q in queries))
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['data']['price'], '12.30')
        self.assertEqual(result['data']['available_stock'], 10)
        self.assertEqual(result['data']['stock_source'], 'sku_stock_fallback')
        self.assertEqual(set(result['data']), {
            'sku_id', 'product_name', 'specification', 'category', 'price', 'currency', 'price_basis',
            'currency_source', 'available_stock', 'stock_source', 'attributes',
        })
        self.assertNotIn('3.21', json.dumps(result))
        self.assertTrue(result['observed_at'])

    def test_ledger_sum_overrides_legacy_stock_and_is_reloaded(self):
        first = Inventory.objects.create(sku=self.sku, warehouse=Warehouse.objects.create(name='A', code='A'),
                                         quantity=8, reserved_quantity=3)
        Inventory.objects.create(sku=self.sku, warehouse=Warehouse.objects.create(name='B', code='B'), quantity=2)
        result = get_product_details(self.sku.pk)
        self.assertEqual(result['data']['available_stock'], 7)
        self.assertEqual(result['data']['stock_source'], 'inventory_ledger')
        first.quantity = 5
        first.save()
        self.sku.price = '13.40'
        self.sku.save()
        result = get_product_details(self.sku.pk)
        self.assertEqual(result['data']['available_stock'], 4)
        self.assertEqual(result['data']['price'], '13.40')

    def test_exhausted_ledger_does_not_revive_legacy_stock(self):
        Inventory.objects.create(sku=self.sku, warehouse=Warehouse.objects.create(name='A', code='A'),
                                 quantity=8, reserved_quantity=8)
        self.assertEqual(get_product_details(self.sku.pk)['status'], 'no_match')

    def test_hidden_missing_and_empty_stock_have_same_public_result(self):
        self.sku.is_launched = False
        self.sku.save()
        hidden = get_product_details(self.sku.pk)
        missing = get_product_details(2147483647)
        self.sku.is_launched, self.sku.stock = True, 0
        self.sku.save()
        empty = get_product_details(self.sku.pk)
        for result in (hidden, missing, empty):
            self.assertEqual(result['status'], 'no_match')
            self.assertIsNone(result['data'])
            self.assertNotIn('sku_id', result)

    def test_attributes_are_public_bounded_and_redacted(self):
        public = ProductAttribute.objects.create(name='配料', code='ingredients', attribute_type='text')
        private = ProductAttribute.objects.create(name='内部成本', code='internal_cost', attribute_type='text')
        ProductAttributeValue.objects.create(attribute=public, spu=self.spu, value_text='绿茶 联系人：张三 13800138000')
        ProductAttributeValue.objects.create(attribute=private, sku=self.sku, value_text='内部合同机密')
        result = get_product_details(self.sku.pk)
        attrs = result['data']['attributes']
        self.assertEqual(len(attrs), 1)
        self.assertNotIn('13800138000', attrs[0]['value_text'])
        self.assertNotIn('张三', attrs[0]['value_text'])
        self.assertNotIn('内部合同机密', json.dumps(result, ensure_ascii=False))

    def test_strict_ids_fail_before_database_access(self):
        with self.assertNumQueries(0):
            for value in (True, False, '1', 1.0, 0, -1, None, 2147483648):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    get_product_details(value)

    def test_management_bridge_outputs_json_and_sanitizes_database_failure(self):
        output = io.StringIO()
        call_command('mcp_product_details', sku_id=self.sku.pk, stdout=output)
        self.assertEqual(json.loads(output.getvalue())['status'], 'success')
        with patch('support_ai.management.commands.mcp_product_details.get_product_details',
                   side_effect=OperationalError('secret-password-and-host')):
            output = io.StringIO()
            call_command('mcp_product_details', sku_id=self.sku.pk, stdout=output)
        result = json.loads(output.getvalue())
        self.assertEqual(result['error_code'], 'SERVICE_UNAVAILABLE')
        self.assertNotIn('secret', output.getvalue())

    def test_management_bridge_rejects_out_of_range_id(self):
        output = io.StringIO()
        call_command('mcp_product_details', sku_id=-1, stdout=output)
        self.assertEqual(json.loads(output.getvalue())['error_code'], 'INVALID_ARGUMENT')
