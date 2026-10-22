import json
from unittest.mock import patch
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone

from goods.models import Catalog, SKU, SPU
from orders.models import OrderGoods, OrderInfo, PreSaleOrder, TrialOrder
from tea_saas.utils import jwt_encode
from users.models import Permission, Role, RolePermission, UserProfile, UserRole
from .models import Conversation, Message, Review, ReviewModeration


class EngagementTests(TestCase):
    def setUp(self):
        redis = patch('orders.views.get_redis_connection')
        redis.start()
        self.addCleanup(redis.stop)

    @classmethod
    def setUpTestData(cls):
        cls.buyer = UserProfile.objects.create(username='engbuyer', is_active=True)
        cls.other = UserProfile.objects.create(username='engother', is_active=True)
        cls.shop = UserProfile.objects.create(username='engshop', user_type='merchant', shop_name='测试店一', is_active=True)
        cls.shop2 = UserProfile.objects.create(username='engshop2', user_type='merchant', shop_name='测试店二', is_active=True)
        cls.admin = UserProfile.objects.create(username='engadmin', is_active=True)
        role, _ = Role.objects.get_or_create(code='admin', defaults={'name':'eng test admin'})
        permission, _ = Permission.objects.get_or_create(code='goods_manage', defaults={'name':'eng test goods'})
        RolePermission.objects.get_or_create(role=role, permission=permission)
        UserRole.objects.get_or_create(role=role, user_profile=cls.admin)
        category = Catalog.objects.create(name='测试茶')
        cls.spu = SPU.objects.create(name='测试商品', catalog=category, merchant=cls.shop)
        cls.spu2 = SPU.objects.create(name='测试商品', catalog=category, merchant=cls.shop2)
        cls.sku = cls.make_sku(cls.spu, '150g')
        cls.sku2 = cls.make_sku(cls.spu, '500g')
        cls.foreign = cls.make_sku(cls.spu2, '150g')

    @staticmethod
    def make_sku(spu, name):
        return SKU.objects.create(spu=spu, name=name, caption='', price=10, market_price=12, cost_price=5, stock=10)

    def call(self, path, user=None, data=None, method=None):
        headers = {'HTTP_AUTHORIZATION': jwt_encode({'id':user.pk})} if user else {}
        url = '/v1/engagement/' + path
        if method == 'DELETE':
            return self.client.delete(url, **headers)
        if data is not None:
            return self.client.post(url, json.dumps(data), content_type='application/json', **headers)
        return self.client.get(url, **headers)

    def order(self, user=None, sku=None, kind='standard', status=4):
        order = OrderInfo.objects.create(user_profile=user or self.buyer, order_id='eng-%s' % OrderInfo.objects.count(),
            order_type=kind, status=status if kind == 'standard' else None, total_amount=10, total_count=1,
            freight=0, receiver='Test', address='Synthetic', receiver_mobile='12345678901', tag='Test')
        if kind == 'trial':
            TrialOrder.objects.create(order_info=order, status=status)
        elif kind == 'presale':
            PreSaleOrder.objects.create(order_info=order, status=status, deposit_amount=2, balance_amount=8,
                                        deposit_paid=True, balance_paid=True)
        return OrderGoods.objects.create(order_info=order, sku=sku or self.sku, count=1, price=10)

    def send(self, user=None, sku=None, request='test-request-01', **extra):
        payload = {'sku_id':(sku or self.sku).pk, 'text':'请问这款茶的规格？', 'request_id':request}
        payload.update(extra)
        return self.call('conversations', user or self.buyer, payload)

    def review(self, item=None, user=None, rating=5, text='商品品质符合预期。'):
        return self.call('reviews', user or self.buyer, {'order_item_id':(item or self.order()).pk, 'rating':rating, 'text':text})

    def public(self, sku=None, query=''):
        return self.call('products/%s/reviews%s' % ((sku or self.sku).pk, query))

    def test_resolve_does_not_create_empty_conversation(self):
        data = self.call('conversations/resolve?sku_id=%s' % self.sku.pk, self.buyer).json()['data']
        self.assertIsNone(data['conversation_id'])
        self.assertEqual(Conversation.objects.count(), 0)

    def test_auth_roles_and_disabled_account(self):
        self.assertEqual(self.call('conversations').status_code, 401)
        self.assertEqual(self.call('conversations', self.admin).status_code, 403)
        self.buyer.is_active = False; self.buyer.save()
        self.assertEqual(self.call('conversations', self.buyer).status_code, 401)

    def test_pair_reused_and_different_merchants_separate(self):
        first = self.send().json()['data']['conversation_id']
        second = self.send(sku=self.sku2, request='test-request-02').json()['data']['conversation_id']
        third = self.send(sku=self.foreign, request='test-request-03').json()['data']['conversation_id']
        self.assertEqual(first, second); self.assertNotEqual(first, third)
        self.assertEqual(Conversation.objects.count(), 2)

    def test_send_is_idempotent_and_changed_payload_conflicts(self):
        self.assertEqual(self.send().status_code, 201)
        self.assertEqual(self.send().status_code, 200)
        self.assertEqual(self.send(text='另一个问题').status_code, 409)
        self.assertEqual(Message.objects.count(), 1)

    def test_first_send_failure_rolls_back_conversation(self):
        self.assertEqual(self.send(text=' ').status_code, 400)
        self.assertEqual(Conversation.objects.count(), 0)

    def test_merchant_spoofing_and_foreign_order_denied(self):
        self.assertEqual(self.send(merchant_id=self.shop2.pk).status_code, 409)
        item = self.order(user=self.other)
        self.assertEqual(self.call('conversations/resolve?order_item_id=%s' % item.pk, self.buyer).status_code, 404)
        OrderGoods.objects.filter(pk=item.pk).update(purchase_snapshot={}, merchant_snapshot=None)
        self.assertEqual(self.call('conversations/resolve?order_item_id=%s' % item.pk, self.buyer).status_code, 404)

    def test_nonparticipant_cannot_read_send_or_mark_read(self):
        conv = self.send().json()['data']['conversation_id']
        for user in (self.other, self.shop2):
            self.assertEqual(self.call('conversations/%s/messages' % conv, user).status_code, 404)
            self.assertEqual(self.call('conversations/%s/messages' % conv, user, {'text':'Hi', 'request_id':'foreign-request'}).status_code, 404)
            self.assertEqual(self.call('conversations/%s/read' % conv, user, {'message_id':Message.objects.first().pk}).status_code, 404)

    def test_merchant_reply_and_unread_read_position(self):
        first = self.send().json()['data']; conv = first['conversation_id']; mid = first['message']['id']
        self.assertEqual(self.call('conversations', self.shop).json()['data']['unread_total'], 1)
        self.call('conversations/%s/read' % conv, self.shop, {'message_id':mid})
        self.assertEqual(self.call('conversations', self.shop).json()['data']['unread_total'], 0)
        reply = self.call('conversations/%s/messages' % conv, self.shop, {'text':'这是150g规格', 'request_id':'reply-request-1'})
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(self.call('conversations', self.buyer).json()['data']['unread_total'], 1)
        self.assertEqual(self.call('conversations/%s/messages' % conv, self.buyer).json()['data']['other_read_id'], mid)

    def test_read_pointer_never_moves_backwards_and_foreign_message_rejected(self):
        first = self.send().json()['data']; conv = first['conversation_id']
        second = self.send(request='test-request-02').json()['data']['message']['id']
        self.call('conversations/%s/read' % conv, self.shop, {'message_id':second})
        self.call('conversations/%s/read' % conv, self.shop, {'message_id':first['message']['id']})
        self.assertEqual(Conversation.objects.get(pk=conv).merchant_read_id, second)
        foreign = self.send(sku=self.foreign, request='test-request-03').json()['data']['message']['id']
        self.assertEqual(self.call('conversations/%s/read' % conv, self.shop, {'message_id':foreign}).status_code, 404)

    def test_context_never_includes_receiver_or_phone(self):
        item = self.order()
        result = self.call('conversations', self.buyer, {'order_item_id':item.pk, 'text':'查看订单', 'request_id':'order-request-1'})
        context = result.json()['data']['message']['context']
        self.assertNotIn('receiver', context); self.assertNotIn('address', context)
        self.assertNotIn('12345678901', json.dumps(context))

    def test_cannot_attach_other_shop_or_other_buyer_to_conversation(self):
        conv = self.send().json()['data']['conversation_id']
        payload = {'sku_id':self.foreign.pk, 'text':'other shop', 'request_id':'cross-shop-123'}
        self.assertEqual(self.call('conversations/%s/messages' % conv, self.shop, payload).status_code, 409)
        payload = {'order_item_id':self.order(user=self.other).pk, 'text':'other buyer', 'request_id':'cross-buyer-123'}
        self.assertEqual(self.call('conversations/%s/messages' % conv, self.shop, payload).status_code, 404)

    def test_history_pagination_has_no_overlap_or_omissions(self):
        conv_id = self.send().json()['data']['conversation_id']; conv = Conversation.objects.get(pk=conv_id)
        Message.objects.bulk_create([Message(conversation=conv, sender=self.buyer, text=str(n), request_id='page-%s' % n,
                                             fingerprint='x') for n in range(65)])
        latest = self.call('conversations/%s/messages' % conv_id, self.shop).json()['data']
        older = self.call('conversations/%s/messages?before=%s' % (conv_id, latest['items'][0]['id']), self.shop).json()['data']
        oldest = self.call('conversations/%s/messages?before=%s' % (conv_id, older['items'][0]['id']), self.shop).json()['data']
        all_ids = [row['id'] for chunk in (oldest, older, latest) for row in chunk['items']]
        self.assertEqual(len(all_ids), 66); self.assertEqual(len(set(all_ids)), 66)
        incremental = self.call('conversations/%s/messages?after=%s' % (conv_id, all_ids[0]), self.shop).json()['data']
        self.assertEqual(len(incremental['items']), 30); self.assertTrue(incremental['has_more'])

    def test_message_limits_and_unavailable_recipient(self):
        self.assertEqual(self.send(text='x' * 2001).status_code, 400)
        self.assertEqual(self.send(request='?').status_code, 400)
        self.shop.is_active = False; self.shop.save()
        self.assertEqual(self.send().status_code, 409)

    def test_rate_limit_does_not_reject_idempotent_retry(self):
        for number in range(30):
            self.assertEqual(self.send(request='rate-%08d' % number).status_code, 201)
        self.assertEqual(self.send(request='rate-00000000').status_code, 200)
        self.assertEqual(self.send(request='rate-overflow').status_code, 429)

    def test_review_rating_and_text_validation(self):
        item = self.order()
        for rating in (0, 6, True, '5', 1.5, None):
            self.assertEqual(self.review(item, rating=rating).status_code, 400)
        self.assertEqual(self.review(item, text='少').status_code, 400)
        self.assertEqual(self.review(item, text='x' * 1001).status_code, 400)

    def test_only_owner_completed_order_can_review(self):
        self.assertEqual(self.review(self.order(user=self.other)).status_code, 404)
        for status in (1, 2, 3):
            self.assertEqual(self.review(self.order(status=status)).status_code, 409)
        self.assertEqual(self.review(user=self.shop).status_code, 403)

    def test_trial_and_presale_completion_rules(self):
        for status in range(1, 8):
            self.assertEqual(self.review(self.order(kind='trial', status=status)).status_code, 409)
        self.assertEqual(self.review(self.order(kind='trial', status=8)).status_code, 201)
        for status in (1, 2, 3, 4, 5, 7):
            self.assertEqual(self.review(self.order(kind='presale', status=status)).status_code, 409)
        self.assertEqual(self.review(self.order(kind='presale', status=6)).status_code, 201)
        item = self.order(kind='presale', status=6)
        PreSaleOrder.objects.filter(order_info=item.order_info).update(balance_paid=False)
        self.assertEqual(self.review(item).status_code, 409)

    def test_review_idempotency_and_repeat_purchase(self):
        item = self.order()
        self.assertEqual(self.review(item).status_code, 201)
        self.assertEqual(self.review(item).status_code, 200)
        self.assertEqual(self.review(item, rating=1).status_code, 409)
        self.assertEqual(self.review().status_code, 201)
        self.assertEqual(Review.objects.count(), 2)

    def test_historical_missing_snapshot_is_not_guessed(self):
        item = self.order()
        OrderGoods.objects.filter(pk=item.pk).update(purchase_snapshot={}, merchant_snapshot=None)
        self.assertEqual(self.review(item).json()['error_code'], 'HISTORY_NOT_VERIFIED')
        self.assertEqual(self.call('conversations/resolve?order_item_id=%s' % item.pk, self.buyer).status_code, 409)

    def test_snapshot_survives_product_rename_and_merchant_transfer(self):
        item = self.order()
        SPU.objects.filter(pk=self.spu.pk).update(name='新名称', merchant=self.shop2)
        SKU.objects.filter(pk=self.sku.pk).update(name='新规格')
        self.assertEqual(self.review(item).status_code, 201)
        review = Review.objects.get()
        self.assertEqual(review.merchant_id, self.shop.pk)
        self.assertEqual(review.purchase_snapshot['product_name'], '测试商品')
        self.assertEqual(review.purchase_snapshot['specification'], '150g')
        self.assertEqual(self.public().json()['data']['summary']['total'], 0)

    def test_public_aggregation_scope_and_no_cross_shop_merge(self):
        self.review(rating=5); self.review(self.order(sku=self.sku2), rating=3)
        self.review(self.order(sku=self.foreign), rating=1)
        data = self.public().json()['data']
        self.assertEqual(data['summary']['total'], 2); self.assertEqual(data['summary']['average'], 4.0)
        self.assertEqual(self.public(query='?scope=sku').json()['data']['summary']['total'], 1)
        self.assertEqual(self.public(self.foreign).json()['data']['summary']['total'], 1)
        self.spu.refresh_from_db(); self.sku.refresh_from_db()
        self.assertEqual(self.spu.comments, 2); self.assertEqual(self.sku.comments, 1)

    def test_order_item_review_scope_excludes_other_orders_and_buyers(self):
        first, second, foreign = self.order(), self.order(), self.order(user=self.other)
        first_id = self.review(first).json()['data']['id']
        self.review(second)
        self.review(foreign, user=self.other)
        path = 'reviews/mine?order_item_id=%s' % first.pk
        data = self.call(path, self.buyer).json()['data']
        self.assertEqual(data['total'], 1)
        self.assertEqual(data['items'][0]['id'], first_id)
        self.assertEqual(self.call(path, self.other).json()['data']['total'], 0)
        self.assertEqual(self.call(path, self.shop2).json()['data']['total'], 0)
        self.assertEqual(self.call('reviews/mine?order_item_id=%s' % foreign.pk, self.buyer).json()['data']['total'], 0)
        self.assertEqual(self.call('reviewable-items?order_item_id=%s' % first.pk, self.other).json()['data']['total'], 0)

    def test_public_projection_masks_identity_and_plain_text(self):
        self.review(text='<script>alert(1)</script>')
        row = self.public().json()['data']['items'][0]
        self.assertEqual(row['buyer_name'], 'e***')
        for private in ('order_id', 'order_item_id', 'buyer_id', 'receiver', 'address', 'phone'):
            self.assertNotIn(private, row)
        self.assertEqual(row['text'], '<script>alert(1)</script>')

    def test_rating_rounds_half_up_and_delete_endpoints_preserve_purchases(self):
        item = self.order()
        self.review(item, rating=5)
        for stars in (5, 4, 3):
            self.review(rating=stars)
        self.assertEqual(self.public().json()['data']['summary']['average'], 4.3)
        token = jwt_encode({'id':self.shop.pk})
        for path in ('sku/%s' % self.sku.pk, 'spu/%s' % self.spu.pk):
            response = self.client.delete('/v1/goods/merchant/' + path, HTTP_AUTHORIZATION=token)
            self.assertEqual(response.status_code, 409)
        response = self.client.post('/v1/supplier/orders/delete', json.dumps({'order_id':item.order_info_id}),
                                    content_type='application/json', HTTP_AUTHORIZATION=token)
        self.assertEqual(response.status_code, 409)
        self.assertTrue(OrderGoods.objects.filter(pk=item.pk).exists())

    def test_merchant_reply_ownership_and_single_reply(self):
        rid = self.review().json()['data']['id']; path = 'reviews/%s/reply' % rid
        self.assertEqual(self.call(path, self.shop2, {'text':'谢谢'}).status_code, 404)
        self.assertEqual(self.call(path, self.buyer, {'text':'谢谢'}).status_code, 403)
        self.assertEqual(self.call(path, self.shop, {'text':'谢谢'}).status_code, 201)
        self.assertEqual(self.call(path, self.shop, {'text':'谢谢'}).status_code, 200)
        self.assertEqual(self.call(path, self.shop, {'text':'修改回复'}).status_code, 409)
        self.assertEqual(self.public().json()['data']['items'][0]['reply']['text'], '谢谢')

    def test_report_idempotent_and_cannot_hide_from_merchant(self):
        rid = self.review(rating=1).json()['data']['id']; path = 'reviews/%s/report' % rid
        self.assertEqual(self.call(path, self.other, {'reason':'包含不适当内容'}).status_code, 201)
        self.assertEqual(self.call(path, self.other, {'reason':'包含不适当内容'}).status_code, 200)
        self.assertEqual(self.call(path, self.shop2, {'reason':'包含不适当内容'}).status_code, 404)
        self.assertEqual(self.call('moderation/%s' % rid, self.shop, {'is_visible':False, 'reason':'随意隐藏差评'}).status_code, 403)
        self.assertEqual(self.public().json()['data']['summary']['total'], 1)

    def test_platform_hide_restore_audited_and_counts_recomputed(self):
        rid = self.review().json()['data']['id']; path = 'moderation/%s' % rid
        self.assertEqual(self.call(path, self.admin, {'is_visible':False, 'reason':'短'}).status_code, 400)
        self.assertEqual(self.call(path, self.admin, {'is_visible':False, 'reason':'经核查包含违规内容'}).status_code, 200)
        self.assertEqual(self.public().json()['data']['summary'], {'total':0, 'average':None, 'distribution':{str(i):0 for i in range(1,6)}})
        self.sku.refresh_from_db(); self.assertEqual(self.sku.comments, 0)
        self.assertEqual(self.call(path, self.admin, {'is_visible':True, 'reason':'复核后恢复公开展示'}).status_code, 200)
        self.assertEqual(ReviewModeration.objects.count(), 2)
        self.assertEqual(self.public().json()['data']['summary']['total'], 1)

    def test_hidden_review_still_present_for_buyer_and_owner_merchant(self):
        rid = self.review().json()['data']['id']
        Review.objects.filter(pk=rid).update(is_visible=False)
        self.assertFalse(self.call('reviews/mine', self.buyer).json()['data']['items'][0]['is_visible'])
        self.assertEqual(self.call('reviews/mine', self.shop2).json()['data']['total'], 0)
        self.assertEqual(self.call('reviews/%s/reply' % rid, self.shop, {'text':'谢谢'}).status_code, 409)

    def test_moderation_pagination_uses_stable_newest_first_order(self):
        ids = [self.review().json()['data']['id'] for _ in range(3)]
        rows = self.call('moderation', self.admin).json()['data']['items']
        self.assertEqual([row['id'] for row in rows], list(reversed(ids)))

    def test_hide_order_preserves_review_and_rejects_nonowner(self):
        item = self.order(); self.review(item)
        url = '/v1/orders/%s/delete' % self.buyer.username
        response = self.client.post(url, json.dumps({'order_id':item.order_info_id}), content_type='application/json',
                                    HTTP_AUTHORIZATION=jwt_encode({'id':self.buyer.pk}))
        self.assertEqual(response.status_code, 200)
        item.order_info.refresh_from_db(); self.assertTrue(item.order_info.buyer_hidden)
        self.assertEqual(Review.objects.count(), 1); self.assertEqual(self.public().json()['data']['summary']['total'], 1)
        response = self.client.get('/v1/orders/%s' % self.buyer.username, HTTP_AUTHORIZATION=jwt_encode({'id':self.buyer.pk}))
        self.assertEqual(response.json()['data']['orders_list'], [])
        with self.assertRaises(ProtectedError):
            item.order_info.delete()
        with self.assertRaises(ProtectedError):
            self.sku.delete()

    def test_order_list_includes_review_eligibility_and_contact_flags(self):
        item = self.order()
        response = self.client.get('/v1/orders/%s' % self.buyer.username, HTTP_AUTHORIZATION=jwt_encode({'id':self.buyer.pk}))
        data = response.json()['data']['orders_list'][0]
        self.assertTrue(data['is_completed']); self.assertTrue(data['order_sku'][0]['can_review'])
        self.assertTrue(data['order_sku'][0]['can_contact']); self.assertEqual(data['order_sku'][0]['id'], item.pk)

    def test_invalid_json_methods_and_cursors(self):
        response = self.client.post('/v1/engagement/reviews', '[]', content_type='application/json', HTTP_AUTHORIZATION=jwt_encode({'id':self.buyer.pk}))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.call('reviews', self.buyer, method='DELETE').status_code, 405)
        conv = self.send().json()['data']['conversation_id']
        self.assertEqual(self.call('conversations/%s/messages?after=-1' % conv, self.buyer).status_code, 400)
        self.assertEqual(self.call('conversations/%s/messages?after=1&before=2' % conv, self.buyer).status_code, 400)
        self.assertEqual(self.public(query='?page=bad').status_code, 400)

    def test_public_pages_render_and_no_ai_dependency(self):
        for page in ('buyer_messages', 'merchant_messages', 'buyer_reviews', 'merchant_reviews', 'admin_reviews', 'product_details'):
            self.assertEqual(self.client.get('/%s.html' % page).status_code, 200)
        from support_ai.models import SupportConversation
        self.send(); self.assertEqual(SupportConversation.objects.count(), 0)

    def test_database_constraints_enforce_single_review_and_star_bounds(self):
        self.review(); row = Review.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Review.objects.filter(pk=row.pk).update(rating=6)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Conversation.objects.create(buyer=self.buyer, merchant=self.shop)
            Conversation.objects.create(buyer=self.buyer, merchant=self.shop)
