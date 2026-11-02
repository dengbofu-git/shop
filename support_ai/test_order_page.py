"""Current displayed-page identity against an explicitly isolated Redis fixture."""
import json
import os
import uuid
from unittest import skipUnless
from unittest.mock import patch
from django.test import TestCase
from redis import Redis
from orders.models import OrderInfo
from users.models import UserProfile
from .context import commit_turn
from .models import SupportConversation, SupportTurn
from .order_queries import OrderQueryContext, query_orders
from .order_contracts import rule_order_query
from .order_page import key, load, publish


@skipUnless(os.getenv('CART_TEST_REDIS_URL'), 'Requires isolated Redis')
class DisplayedOrderPageTests(TestCase):
    def setUp(self):
        self.user=UserProfile.objects.create(username='pagebuyer',is_active=True)
        self.other=UserProfile.objects.create(username='pageother',is_active=True)
        self.conversation=SupportConversation.objects.create(user=self.user)
        self.redis=Redis.from_url(os.environ['CART_TEST_REDIS_URL'])
        connection=patch('support_ai.order_page.get_redis_connection',return_value=self.redis)
        connection.start();self.addCleanup(connection.stop)
        self.addCleanup(lambda:self.redis.delete(key(self.user.pk,self.conversation.pk)))
        for i in range(3):self.make_order('PRIVATE-PAGE-'+str(i))

    def make_order(self,identity,owner=None):
        return OrderInfo.objects.create(order_id=identity,user_profile=owner or self.user,total_amount=10,
            total_count=1,freight=0,status=1,receiver='Synthetic',address='Synthetic',receiver_mobile='000',tag='Test')

    def show(self,message='查询最近订单',request_id=None,query=None):
        self.conversation.refresh_from_db()
        context=OrderQueryContext(owner_id=self.user.pk,conversation_id=self.conversation.pk)
        result=query_orders(query or rule_order_query(message),context,message)
        response={'answer':result['data']['answer'],'intent':'after_sales','order_result':{'status':result['status'],**result['data']}}
        with self.captureOnCommitCallbacks(execute=True):
            commit_turn(self.user,self.conversation,self.conversation.revision,request_id or uuid.uuid4(),
                message,message,response,order_page=context.pending_order_page)
        return context,result

    def test_new_orders_do_not_shift_displayed_position_and_state_is_fresh(self):
        context,_=self.show()
        expected=context.pending_order_page['ids'][1]
        self.make_order('NEW-AFTER-DISPLAY')
        OrderInfo.objects.filter(pk=expected).update(status=3)
        result=query_orders(rule_order_query('第二笔发货了吗'),
            OrderQueryContext(owner_id=self.user.pk,conversation_id=self.conversation.pk),'第二笔发货了吗')
        self.assertEqual(result['status'],'success')
        self.assertEqual(result['data']['orders'][0]['shipping_status'],'shipped')
        self.assertNotIn('PRIVATE-PAGE',json.dumps(result))
        self.assertGreater(self.redis.ttl(key(self.user.pk,self.conversation.pk)),0)
        self.assertLessEqual(self.redis.ttl(key(self.user.pk,self.conversation.pk)),86400)

    def test_hidden_or_expired_or_out_of_page_requires_clarification(self):
        context,_=self.show()
        OrderInfo.objects.filter(pk=context.pending_order_page['ids'][1]).update(buyer_hidden=True)
        for sentence in ('第二笔发货了吗','第四笔什么状态'):
            result=query_orders(rule_order_query(sentence),OrderQueryContext(owner_id=self.user.pk,conversation_id=self.conversation.pk),sentence)
            self.assertEqual(result['status'],'needs_clarification')
        self.redis.expire(key(self.user.pk,self.conversation.pk),0)
        self.assertIsNone(load(self.user.pk,self.conversation.pk))

    def test_foreign_conversation_and_redis_outage_do_not_grant_access(self):
        self.show()
        self.assertIsNone(load(self.other.pk,self.conversation.pk))
        with patch('support_ai.order_page.get_redis_connection',side_effect=RuntimeError('synthetic outage')):
            for sentence,status in [('第二笔发货了吗','needs_clarification'),('查询最近订单','success')]:
                result=query_orders(rule_order_query(sentence),OrderQueryContext(owner_id=self.user.pk,conversation_id=self.conversation.pk),sentence)
                self.assertEqual(result['status'],status)

    def test_failed_save_does_not_publish_unseen_page(self):
        self.show()
        before=self.redis.get(key(self.user.pk,self.conversation.pk))
        self.conversation.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True), patch('support_ai.context.SupportTurn.objects.create',side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                commit_turn(self.user,self.conversation,self.conversation.revision,uuid.uuid4(),'new','new',
                    {'answer':'new','intent':'after_sales'},order_page={'ids':['UNSEEN'],'query':{}})
        self.assertEqual(self.redis.get(key(self.user.pk,self.conversation.pk)),before)

    def test_old_replay_and_late_publish_never_replace_new_page(self):
        request_id=uuid.uuid4()
        self.show(request_id=request_id)
        self.show('查询全部订单')
        before=self.redis.get(key(self.user.pk,self.conversation.pk))
        publish(self.user.pk,self.conversation.pk,1,{'ids':['STALE'],'query':{}})
        self.assertEqual(self.redis.get(key(self.user.pk,self.conversation.pk)),before)
        self.conversation.refresh_from_db()
        with self.captureOnCommitCallbacks(execute=True):
            commit_turn(self.user,self.conversation,self.conversation.revision,request_id,
                '查询最近订单','查询最近订单',{'answer':'ignored'},order_page={'ids':['STALE'],'query':{}})
        self.assertEqual(self.redis.get(key(self.user.pk,self.conversation.pk)),before)

    def test_new_empty_query_invalidates_previous_page(self):
        self.show()
        self.show('查询2020-01-01至2020-01-02的全部订单')
        self.assertIsNone(load(self.user.pk,self.conversation.pk))

    def test_next_page_replaces_displayed_positions(self):
        from .order_contracts import OrderQuery, OrderSelector
        for i in range(21):self.make_order('PAGINATED-'+str(i))
        first,_=self.show('查询全部订单')
        following,_=self.show('下一页',query=OrderQuery(selector=OrderSelector(type='all'),page='next'))
        page=load(self.user.pk,self.conversation.pk)
        self.assertEqual(page['ids'],following.pending_order_page['ids'])
        self.assertEqual(len(page['ids']),4)
        self.assertTrue(set(page['ids']).isdisjoint(first.pending_order_page['ids']))

    def test_committed_new_page_with_failed_cache_write_invalidates_old_binding(self):
        self.show()
        with patch('support_ai.order_page.get_redis_connection',side_effect=RuntimeError('synthetic outage')):
            self.show('查询全部订单')
        self.assertIsNone(load(self.user.pk,self.conversation.pk))
        message='第二笔发货了吗'
        result=query_orders(rule_order_query(message),OrderQueryContext(owner_id=self.user.pk,
            conversation_id=self.conversation.pk),message)
        self.assertEqual(result['status'],'needs_clarification')
