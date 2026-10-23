"""Merchant feed isolation and real task semantics, using synthetic test records."""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from engagement.models import Conversation, Message
from goods.models import Catalog, SKU, SPU
from logistics.models import LogisticsProvider, ShippingOrder
from orders.models import OrderGoods, OrderInfo, PreSaleOrder, TrialOrder
from tea_saas.utils import jwt_encode
from users.models import Role, UserProfile, UserRole
from .models import SupplierSettlement
from .workbench import build_workbench_feed


class WorkbenchFeedTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = UserProfile.objects.create(username='feed-buyer', is_active=True)
        cls.shop = UserProfile.objects.create(username='feed-shop', user_type='merchant', is_active=True)
        cls.other = UserProfile.objects.create(username='feed-other', user_type='merchant', is_active=True)
        catalog = Catalog.objects.create(name='测试茶')
        cls.skus = []
        for shop in (cls.shop, cls.other):
            spu = SPU.objects.create(name=shop.username, merchant=shop, catalog=catalog)
            cls.skus.append(SKU.objects.create(name=shop.username, spu=spu, price=10, cost_price=5, market_price=12))
        cls.provider = LogisticsProvider.objects.create(name='测试物流', code='feed-test')

    def order(self, key, *, status=2, kind='standard', skus=None):
        order = OrderInfo.objects.create(
            order_id=key, user_profile=self.buyer, order_type=kind, status=status,
            total_amount=10, total_count=1, freight=0, receiver='测试', address='私密地址',
            receiver_mobile='00000000000', tag='测试')
        for sku in skus or [self.skus[0]]:
            OrderGoods.objects.create(order_info=order, sku=sku, count=1, price=10)
        return order

    def message(self, conversation, text='测试买家咨询', sender=None):
        return Message.objects.create(conversation=conversation, sender=sender or self.buyer,
                                      text=text, request_id=str(Message.objects.count()), fingerprint='test')

    def shipment(self, order):
        return ShippingOrder.objects.create(order_info=order, provider=self.provider,
            tracking_number='T-' + order.pk, status=2, receiver_name='测试',
            receiver_phone='00000000000', receiver_address='私密地址')

    def get_feed(self, user):
        token = jwt_encode({'id': user.pk, 'username': user.username})
        if isinstance(token, bytes):
            token = token.decode()
        return self.client.get('/v1/supplier/workbench-feed', HTTP_AUTHORIZATION='Bearer ' + token)

    def test_all_pending_orders_deduplicate_lines_and_ignore_analytics_period(self):
        old = self.order('old', skus=[self.skus[0], self.skus[0]])
        OrderInfo.objects.filter(pk=old.pk).update(created_time=timezone.now() - timedelta(days=800))
        self.order('unpaid', status=1)
        self.order('complete', status=4)
        self.order('foreign', skus=[self.skus[1]])
        self.assertEqual(build_workbench_feed(self.shop)['todos']['unshipped'], 1)

    def test_subtype_status_and_full_presale_payment_are_required(self):
        for status in (1, 2, 4, 6, 8):
            TrialOrder.objects.create(order_info=self.order('trial-' + str(status), kind='trial'), status=status)
        for key, status, deposit, balance in [('full', 4, True, True), ('part', 4, True, False),
                                             ('none', 4, False, False), ('cancel', 7, True, True)]:
            PreSaleOrder.objects.create(order_info=self.order(key, kind='presale'), status=status,
                deposit_amount=2, balance_amount=8, deposit_paid=deposit, balance_paid=balance)
        self.order('missing-detail', kind='trial')
        self.assertEqual(build_workbench_feed(self.shop)['todos']['unshipped'], 2)

    def test_recorded_seller_precedes_current_owner_and_legacy_fallback_is_scoped(self):
        original = self.order('original')
        legacy = self.order('legacy')
        OrderGoods.objects.filter(order_info=legacy).update(merchant_snapshot=None)
        SPU.objects.filter(pk=self.skus[0].spu_id).update(merchant=self.other)
        self.assertEqual(build_workbench_feed(self.shop)['todos']['unshipped'], 1)
        self.assertEqual(build_workbench_feed(self.other)['todos']['unshipped'], 1)
        self.assertEqual(build_workbench_feed(self.shop)['messages'][0]['order_id'], original.pk)

    def test_settlement_count_uses_own_pending_rows_only(self):
        order = self.order('settlements')
        for shop, status in [(self.shop, 'pending'), (self.shop, 'settled'),
                             (self.shop, 'cancelled'), (self.other, 'pending')]:
            SupplierSettlement.objects.create(supplier=shop, order_info=order, amount=10, status=status)
        feed = build_workbench_feed(self.shop)
        self.assertEqual(feed['todos']['settlement'], 1)
        self.assertEqual(feed['total'], 2)
        self.assertIsNone(feed['todos']['product_review'])
        self.assertIsNone(feed['todos']['after_sales'])

    def test_unread_counts_conversations_not_messages_and_reads_do_not_mutate(self):
        conversation = Conversation.objects.create(buyer=self.buyer, merchant=self.shop)
        read = self.message(conversation, '已读')
        conversation.merchant_read_id = read.pk
        conversation.save()
        self.message(conversation)
        self.message(conversation)
        self.message(conversation, sender=self.shop, text='商家回复')
        foreign = Conversation.objects.create(buyer=self.buyer, merchant=self.other)
        self.message(foreign, '别家私密咨询')
        feed = self.get_feed(self.shop)
        self.assertEqual(feed.status_code, 200)
        self.assertEqual(feed.json()['data']['todos']['consultations'], 1)
        self.assertNotContains(feed, '别家私密咨询')
        self.assertNotContains(feed, '商家回复')
        conversation.refresh_from_db()
        self.assertEqual(conversation.merchant_read_id, read.pk)
        conversation.merchant_read_id = Message.objects.filter(conversation=conversation).last().pk
        conversation.save()
        self.assertEqual(build_workbench_feed(self.shop)['todos']['consultations'], 0)

    def test_shipments_exclude_foreign_and_ambiguous_historical_mixed_orders(self):
        own = self.order('own-shipping', status=3)
        foreign = self.order('foreign-shipping', status=3, skus=[self.skus[1]])
        mixed = self.order('mixed-shipping', status=3, skus=self.skus)
        for order in (own, foreign, mixed):
            self.shipment(order)
        feed = self.get_feed(self.shop)
        shipments = [row for row in feed.json()['data']['messages'] if row['kind'] == 'shipping']
        self.assertEqual([row['order_id'] for row in shipments], [own.pk])
        self.assertNotContains(feed, '私密地址')
        self.assertNotContains(feed, 'receiver_phone')
        self.assertNotContains(feed, foreign.pk)

    def test_recent_feed_combines_real_records_and_caps_at_eight(self):
        for index in range(8):
            self.order('order-%d' % index)
        conversation = Conversation.objects.create(buyer=self.buyer, merchant=self.shop)
        for index in range(6):
            self.message(conversation, '咨询-%d' % index)
        feed = build_workbench_feed(self.shop)
        self.assertEqual(len(feed['messages']), 8)
        self.assertEqual([row['created_at'] for row in feed['messages']],
                         sorted([row['created_at'] for row in feed['messages']], reverse=True))
        self.assertEqual({row['kind'] for row in feed['messages']}, {'inquiry', 'order'})
        self.assertEqual(feed['total'], 9)

    def test_empty_shop_has_real_zeros_empty_messages_and_unknown_workflows(self):
        feed = build_workbench_feed(self.other)
        self.assertEqual(feed['total'], 0)
        self.assertEqual(feed['messages'], [])
        self.assertEqual(feed['todos'], dict(unshipped=0, settlement=0, consultations=0,
                                            product_review=None, after_sales=None))

    def test_endpoint_denies_anonymous_customer_inactive_and_platform_accounts(self):
        self.assertEqual(self.client.get('/v1/supplier/workbench-feed').status_code, 401)
        self.assertEqual(self.get_feed(self.buyer).status_code, 403)
        self.other.is_active = False
        self.other.save()
        self.assertEqual(self.get_feed(self.other).status_code, 401)
        admin = Role.objects.create(code='admin', name='平台管理员', is_active=True)
        UserRole.objects.create(user_profile=self.shop, role=admin)
        self.assertEqual(self.get_feed(self.shop).status_code, 403)

    def test_method_cache_headers_and_query_count(self):
        self.order('query-count')
        self.assertEqual(self.client.post('/v1/supplier/workbench-feed').status_code, 405)
        response = self.get_feed(self.shop)
        self.assertEqual(response.status_code, 200)
        self.assertIn('no-store', response['Cache-Control'])
        with self.assertNumQueries(6):
            build_workbench_feed(self.shop)
