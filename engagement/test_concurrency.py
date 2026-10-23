"""Real row-lock tests; SQLite cannot validate these guarantees."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless

from django.db import close_old_connections, connection
from django.test import Client, TransactionTestCase

from tea_saas.utils import jwt_encode
from .models import Conversation, Message, Review
from .tests import EngagementTests


@skipUnless(connection.vendor == 'mysql', 'Requires isolated MySQL row locks')
class EngagementConcurrencyTests(TransactionTestCase):
    make_sku = staticmethod(EngagementTests.make_sku)
    order = EngagementTests.order

    def setUp(self):
        EngagementTests.setUpTestData.__func__(type(self))

    def parallel(self, path, payloads):
        barrier = Barrier(len(payloads))
        user_id = self.buyer.pk
        def worker(data):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                response = Client().post('/v1/engagement/' + path, json.dumps(data), content_type='application/json',
                                         HTTP_AUTHORIZATION=jwt_encode({'id':user_id}))
                return response.status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=len(payloads)) as pool:
            return list(pool.map(worker, payloads))

    def test_first_message_race_creates_one_pair_and_message(self):
        data = {'text':'并发发送测试消息', 'sku_id':self.sku.pk, 'request_id':'concurrent-request-1'}
        self.assertCountEqual(self.parallel('conversations', [data, data]), [201, 200])
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(Message.objects.count(), 1)

    def test_hide_and_new_send_preserve_pair_and_history_under_row_lock(self):
        from django.db import transaction
        from threading import Event
        conv = Conversation.objects.create(buyer=self.buyer, merchant=self.shop)
        entered = Event()
        def send():
            close_old_connections()
            try:
                entered.set()
                return Client().post('/v1/engagement/conversations', json.dumps({
                    'merchant_id': self.shop.pk, 'text': '继续咨询', 'request_id': 'visibility-lock-send'}),
                    content_type='application/json', HTTP_AUTHORIZATION=jwt_encode({'id': self.buyer.pk})).status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=1) as pool:
            # Hide and send serialize on the same pair, including POST conversations.
            with transaction.atomic():
                Conversation.objects.select_for_update().get(pk=conv.pk)
                Conversation.objects.filter(pk=conv.pk).update(buyer_hidden=True, merchant_hidden=True)
                result = pool.submit(send)
                self.assertTrue(entered.wait(timeout=10))
            self.assertEqual(result.result(timeout=20), 201)
        conv.refresh_from_db()
        self.assertFalse(conv.buyer_hidden)
        self.assertFalse(conv.merchant_hidden)
        self.assertEqual(Conversation.objects.count(), 1)
        self.assertEqual(conv.messages.count(), 1)

    def test_same_order_item_race_creates_one_review(self):
        item = self.order()
        data = {'order_item_id':item.pk, 'rating':5, 'text':'并发提交评价测试。'}
        self.assertCountEqual(self.parallel('reviews', [data, data]), [201, 200])
        self.assertEqual(Review.objects.count(), 1)
        self.sku.refresh_from_db(); self.assertEqual(self.sku.comments, 1)

    def test_different_items_keep_spu_and_sku_counts_consistent(self):
        items = [self.order(), self.order()]
        payloads = [{'order_item_id':item.pk, 'rating':4, 'text':'并发评价汇总测试。'} for item in items]
        self.assertEqual(self.parallel('reviews', payloads), [201, 201])
        self.spu.refresh_from_db(); self.sku.refresh_from_db()
        self.assertEqual(self.spu.comments, 2); self.assertEqual(self.sku.comments, 2)
