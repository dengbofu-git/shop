"""Synthetic object-scope matrix; no external carrier calls or business data."""
from django.test import TestCase
from orders.test_reservations import Fixtures
from orders.models import OrderInfo, OrderGoods
from inventory.models import Warehouse, Inventory
from users.models import Role, Permission, RolePermission, UserRole
from tea_saas.utils import jwt_encode
from .models import LogisticsProvider, ShippingOrder


class FulfillmentScopeTests(Fixtures, TestCase):
    def setUp(self):
        self.seed()
        self.order = OrderInfo.objects.create(order_id='scope-order', user_profile=self.buyers[0],
            total_amount=10, total_count=1, freight=0, receiver='Synthetic', address='Synthetic',
            receiver_mobile='00000000000', tag='test')
        self.line = OrderGoods.objects.create(order_info=self.order, sku=self.skus[0], count=1,
            price=10, merchant_snapshot=self.shops[0])
        provider = LogisticsProvider.objects.create(name='Synthetic', code='TEST')
        ShippingOrder.objects.create(order_info=self.order, provider=provider, tracking_number='PRIVATE-TRACK',
            receiver_name='Synthetic', receiver_phone='00000000000', receiver_address='Synthetic')
        self.url = '/v1/logistics/track/scope-order'
        warehouse = Warehouse.objects.create(name='Synthetic', code='SCOPE', address='Synthetic')
        for sku in self.skus: Inventory.objects.create(sku=sku, warehouse=warehouse, quantity=10)

    def get(self, url, user=None):
        headers = {} if user is None else {'HTTP_AUTHORIZATION': 'Bearer '+jwt_encode({'id':user.pk})}
        return self.client.get(url, **headers)

    def grant(self, user, permission, role='admin'):
        r, _ = Role.objects.get_or_create(code=role, defaults={'name':role})
        p, _ = Permission.objects.get_or_create(code=permission, defaults={'name':permission})
        UserRole.objects.get_or_create(user_profile=user, role=r)
        link, _ = RolePermission.objects.get_or_create(role=r, permission=p)
        return link

    def test_buyer_own_and_cross_buyer_guesses(self):
        self.assertEqual(self.get(self.url, self.buyers[0]).status_code, 200)
        foreign = self.get(self.url, self.buyers[1])
        missing = self.get('/v1/logistics/track/missing', self.buyers[1])
        self.assertEqual((foreign.status_code,foreign.json()), (missing.status_code,missing.json()))
        self.assertEqual(foreign.status_code, 404)

    def test_merchant_snapshot_and_cross_store(self):
        self.skus[0].spu.merchant=self.shops[1];self.skus[0].spu.save()
        self.assertEqual(self.get(self.url,self.shops[0]).status_code,200)
        self.assertEqual(self.get(self.url,self.shops[1]).status_code,404)

    def test_mixed_order_is_buyer_visible_but_no_whole_store_access(self):
        OrderGoods.objects.create(order_info=self.order,sku=self.skus[1],count=1,price=10)
        self.assertEqual(self.get(self.url,self.buyers[0]).status_code,200)
        for shop in self.shops:self.assertEqual(self.get(self.url,shop).status_code,404)

    def test_platform_needs_live_permission_even_for_own_order(self):
        link=self.grant(self.buyers[0],'data_view')
        self.assertEqual(self.get(self.url,self.buyers[0]).status_code,403)
        grant=self.grant(self.buyers[0],'logistics_manage')
        self.assertEqual(self.get(self.url,self.buyers[0]).status_code,200)
        grant.delete()
        self.assertEqual(self.get(self.url,self.buyers[0]).status_code,403)

    def test_anonymous_and_disabled_identities(self):
        self.assertEqual(self.get(self.url).status_code,401)
        for user in (self.buyers[0],self.shops[0]):
            user.is_active=False;user.save()
            self.assertEqual(self.get(self.url,user).status_code,403)

    def test_inventory_and_shared_warehouses_are_platform_only(self):
        for path in ('/v1/inventory/list','/v1/inventory/warehouses'):
            self.assertEqual(self.get(path).status_code,401)
            self.assertEqual(self.get(path,self.buyers[0]).status_code,403)
            self.grant(self.shops[0],'inventory_manage',role='supplier')
            self.assertEqual(self.get(path,self.shops[0]).status_code,403)
            grant=self.grant(self.buyers[1],'inventory_manage')
            self.assertEqual(self.get(path,self.buyers[1]).status_code,200)
            grant.delete()
            self.assertEqual(self.get(path,self.buyers[1]).status_code,403)

    def test_disabled_platform_cannot_read_stock(self):
        self.grant(self.buyers[1],'inventory_manage')
        self.buyers[1].is_active=False;self.buyers[1].save()
        self.assertEqual(self.get('/v1/inventory/list',self.buyers[1]).status_code,403)
