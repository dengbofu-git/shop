"""Real Redis + isolated test database, including crash windows and cart races."""
import json
import os
import uuid
from unittest import skipUnless
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor

from django.test import TestCase
from django.db import transaction
from redis import Redis
from redis.exceptions import ConnectionError
from carts.atomic_add import add_items, compare_set
from carts.state import checkout_snapshot, CLEAN_SCRIPT
from .test_reservations import Fixtures
from .models import CartCleanupTask, CheckoutRequest, OrderInfo, StockHold
from .reservations import create_orders, ReservationError
from .cart_cleanup import process_task, drain_cleanup


@skipUnless(os.environ.get('CART_TEST_REDIS_URL'), 'Requires explicitly isolated Redis')
class CartCleanupTests(Fixtures, TestCase):
    def setUp(self):
        self.seed()
        self.redis = Redis.from_url(os.environ['CART_TEST_REDIS_URL'])
        self.user = self.buyers[0]
        self.key = 'carts_' + self.user.username
        self.sid = str(self.skus[0].pk)
        self.redis.delete(self.key)
        self.add(5)
        self.patch = patch('carts.views.get_redis_connection', return_value=self.redis)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def tearDown(self):
        self.redis.delete(self.key)
        for key in self.redis.scan_iter('cart-add-receipt:' + self.user.username + ':*'):
            self.redis.delete(key)
        self.redis.close()

    def add(self, count):
        return add_items(self.redis, self.user.username, uuid.uuid4().hex, 'synthetic',
                         [{'sku_id':self.sid, 'count':count, 'available_stock':100}])

    def row(self):
        value = self.redis.hget(self.key, self.sid)
        return json.loads(value) if value else None

    def place(self):
        rows = {int(k):json.loads(v) for k,v in checkout_snapshot(self.redis,self.user.username).items()}
        orders = create_orders(self.user, uuid.uuid4().hex, 'cart-test', self.addresses[0].pk,
                               {int(self.sid):rows[int(self.sid)]['count']}, '127.0.0.1', cart_snapshots=rows)
        return orders[0], CartCleanupTask.objects.get(checkout=orders[0].checkout_request)

    def test_order_hold_and_task_roll_back_together(self):
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.place()
                raise RuntimeError('simulated SQL transaction failure')
        self.assertEqual((OrderInfo.objects.count(), StockHold.objects.count(), CartCleanupTask.objects.count()), (0,0,0))
        self.assertEqual(self.row()['count'],5)

    def test_new_additions_remain_after_repeated_cleanup(self):
        order, task = self.place()
        self.add(2)
        process_task(task.pk,self.redis)
        self.assertEqual(self.row()['count'],2)
        process_task(task.pk,self.redis)
        self.assertEqual(self.row()['count'],2)

    def test_crash_after_redis_before_mysql_ack_is_safe(self):
        order, task = self.place()
        self.add(2)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                process_task(task.pk,self.redis)
                raise RuntimeError('crash before SQL acknowledgment')
        task.refresh_from_db()
        self.assertEqual(task.status,'pending')
        self.assertEqual(self.row()['count'],2)
        process_task(task.pk,self.redis)
        self.assertEqual(self.row()['count'],2)

    def test_delete_readd_identical_quantity_has_new_generation(self):
        order, task = self.place()
        self.redis.hdel(self.key,self.sid)
        self.add(5)
        self.assertNotEqual(self.row()['generation'],task.generation)
        process_task(task.pk,self.redis)
        self.assertEqual(self.row()['count'],5)
        task.refresh_from_db()
        self.assertEqual(task.result,'superseded')

    def test_edit_then_add_preserves_new_units(self):
        order, task = self.place()
        before = self.redis.hget(self.key,self.sid)
        after = dict(json.loads(before),count=2)
        self.assertTrue(compare_set(self.redis,self.key,self.sid,before,json.dumps(after)))
        self.add(3)
        process_task(task.pk,self.redis)
        self.assertEqual(self.row()['count'],3)

    def test_redis_outage_retains_task_and_retry_recovers(self):
        order, task = self.place()
        with patch.object(self.redis,'eval',side_effect=ConnectionError('simulated')):
            self.assertFalse(process_task(task.pk,self.redis))
        task.refresh_from_db()
        self.assertEqual((task.status,task.attempts,task.last_error),('pending',1,'ConnectionError'))
        self.assertEqual(OrderInfo.objects.get(pk=order.pk).status,1)
        self.assertEqual(drain_cleanup(conn=self.redis,force=True),1)
        self.assertIsNone(self.row())

    def test_sql_failure_recording_task_rolls_back_order(self):
        with patch('orders.cart_cleanup.CartCleanupTask.objects.create', side_effect=RuntimeError('disk failure')):
            with self.assertRaises(RuntimeError): self.place()
        self.assertFalse(OrderInfo.objects.exists())
        self.assertFalse(CheckoutRequest.objects.exists())
        self.assertFalse(StockHold.objects.exists())

    def test_new_request_cannot_consume_same_snapshot(self):
        self.place()
        # Ignore the SKU-pending guard to exercise consumption ownership itself.
        OrderInfo.objects.update(status=4)
        with self.assertRaises(ReservationError) as error: self.place()
        self.assertEqual(error.exception.code,'CART_CHANGED')
        self.assertEqual(CartCleanupTask.objects.count(),1)

    def test_legacy_row_upgraded_at_checkout_not_get(self):
        self.redis.hset(self.key,self.sid,json.dumps({'count':5,'status':True}))
        before = self.redis.hget(self.key,self.sid)
        response = self.client.get('/v1/carts/'+self.user.username,**self.headers(self.user))
        self.assertEqual(response.status_code,200)
        self.assertEqual(self.redis.hget(self.key,self.sid),before)
        self.place()
        self.assertTrue(self.row()['generation'])

    def test_get_never_reduces_or_deletes_short_stock(self):
        for stock in (3,0):
            self.skus[0].stock=stock
            self.skus[0].save()
            before=self.redis.hget(self.key,self.sid)
            response=self.client.get('/v1/carts/'+self.user.username,**self.headers(self.user)).json()
            self.assertEqual(response['data'][0]['count'],5)
            self.assertEqual(response['data'][0]['available_stock'],stock)
            self.assertTrue(response['data'][0]['stock_shortage'])
            self.assertEqual(self.redis.hget(self.key,self.sid),before)

    def test_stale_edit_cannot_restore_consumed_units(self):
        order, task=self.place()
        before=self.redis.hget(self.key,self.sid)
        process_task(task.pk,self.redis)
        self.assertFalse(compare_set(self.redis,self.key,self.sid,before,json.dumps({'count':6,'status':True})))
        self.assertIsNone(self.row())

    def test_lua_parallel_retries_apply_once(self):
        order,task=self.place()
        self.add(2)
        def clean(_):
            return self.redis.eval(CLEAN_SCRIPT,1,self.key,self.sid,task.generation,str(task.consumed_to))
        with ThreadPoolExecutor(max_workers=6) as pool: list(pool.map(clean,range(12)))
        self.assertEqual(self.row()['count'],2)

    def test_http_commits_order_and_keeps_retry_after_clear_failure(self):
        payload={'settlement_type':'0','address_id':self.addresses[0].pk,'request_id':uuid.uuid4().hex}
        url='/v1/orders/'+self.user.username
        original=self.redis.eval
        def outage(script,*args):
            if script==CLEAN_SCRIPT: raise ConnectionError('simulated')
            return original(script,*args)
        with patch('orders.views.get_redis_connection',return_value=self.redis):
            with patch.object(self.redis,'eval',side_effect=outage), self.captureOnCommitCallbacks(execute=True):
                first=self.client.post(url,payload,content_type='application/json',**self.headers(self.user))
            self.assertEqual(first.status_code,200)
            self.assertEqual(CartCleanupTask.objects.get().status,'pending')
            retry=self.client.post(url,payload,content_type='application/json',**self.headers(self.user))
        self.assertEqual(first.json(),retry.json())
        self.assertEqual(OrderInfo.objects.count(),1)
        self.assertEqual(CartCleanupTask.objects.get().status,'done')
        self.assertIsNone(self.row())

    def test_http_redis_failure_before_order_returns_unavailable(self):
        with patch('orders.views.get_redis_connection',return_value=self.redis), patch.object(self.redis,'eval',side_effect=ConnectionError('simulated')):
            result=self.client.post('/v1/orders/'+self.user.username,{'settlement_type':'0','address_id':self.addresses[0].pk,'request_id':uuid.uuid4().hex},content_type='application/json',**self.headers(self.user))
        self.assertEqual(result.status_code,503)
        self.assertFalse(OrderInfo.objects.exists())
