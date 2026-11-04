"""Login cart badges use SKU fields; all users and Redis keys are synthetic."""
import json
import os
import uuid
from unittest import skipUnless
from unittest.mock import Mock, patch

from django.test import TestCase
from redis import Redis
from redis.exceptions import ConnectionError, ResponseError, TimeoutError

from carts.atomic_add import add_items, receipt_key, request_hash
from tea_saas.utils import md5
from tea_saas.runtime_logging import JsonFormatter
from users.models import UserProfile


class LoginCartFixture:
    def setUp(self):
        self.buyer = UserProfile.objects.create(
            username='Lc'+uuid.uuid4().hex[:8], user_type='customer',
            password=md5('fixture-cart'), is_active=True,
        )

    def login(self, connection, username=None):
        with patch('users.views.get_redis_connection', return_value=connection):
            return self.client.post('/v1/users/login', {
                'username': username or self.buyer.username, 'password': 'fixture-cart',
            }, content_type='application/json').json()

    def assert_success(self, result, count):
        self.assertEqual(result['code'], 200)
        self.assertIn('token', result)
        self.assertEqual(result['carts_count'], count)
        self.assertEqual(result['username'], self.buyer.username)


class LoginCartCountTests(LoginCartFixture, TestCase):
    def connection(self, count=0):
        connection = Mock(spec=Redis)
        connection.hlen.return_value = count
        connection.get.side_effect = ResponseError('WRONGTYPE synthetic cart hash')
        return connection

    def test_empty_cart_is_zero_without_blocking_login(self):
        self.assert_success(self.login(self.connection()), 0)

    def test_cart_badge_counts_sku_entries(self):
        self.assert_success(self.login(self.connection(count=3)), 3)

    def test_case_variant_uses_the_stored_username_cart(self):
        connection = self.connection()
        canonical_key = 'carts_'+self.buyer.username
        connection.hlen.side_effect = lambda key: 2 if key == canonical_key else 0
        self.assert_success(self.login(connection, self.buyer.username.swapcase()), 2)

    def test_unavailable_connection_factory_does_not_block_login(self):
        with patch('users.views.get_redis_connection', side_effect=ConnectionError('synthetic outage')):
            result = self.client.post('/v1/users/login', {
                'username': self.buyer.username, 'password': 'fixture-cart',
            }, content_type='application/json').json()
        self.assert_success(result, 0)

    def test_disconnected_cart_command_does_not_block_login(self):
        connection = self.connection()
        connection.hlen.side_effect = ConnectionError('synthetic outage')
        self.assert_success(self.login(connection), 0)

    def test_cart_timeout_does_not_block_login(self):
        connection = self.connection()
        connection.hlen.side_effect = TimeoutError('synthetic timeout')
        self.assert_success(self.login(connection), 0)

    def test_cart_failure_has_a_distinct_event_without_private_exception_text(self):
        connection = self.connection()
        connection.hlen.side_effect = ConnectionError('synthetic-private-redis-credential')
        with self.assertLogs('users.views', level='WARNING') as captured:
            result = self.login(connection)
        self.assert_success(result, 0)
        text = JsonFormatter().format(captured.records[0])
        self.assertEqual(json.loads(text)['event'], 'users.login.cart_count_unavailable')
        self.assertNotIn('synthetic-private-redis-credential', text)
        self.assertNotIn(self.buyer.username, text)

    def test_wrong_cart_type_does_not_block_login(self):
        connection = self.connection()
        connection.hlen.side_effect = ResponseError('WRONGTYPE synthetic string key')
        self.assert_success(self.login(connection), 0)

    def test_merchant_login_does_not_need_cart_storage(self):
        self.buyer.user_type = 'merchant'
        self.buyer.save(update_fields=['user_type'])
        with patch('users.views.get_redis_connection', side_effect=AssertionError('cart must not be read')):
            result = self.client.post('/v1/users/login', {
                'username': self.buyer.username, 'password': 'fixture-cart',
            }, content_type='application/json').json()
        self.assert_success(result, 0)
        self.assertEqual(result['redirect_url'], '/merchant_dashboard.html')


@skipUnless(os.environ.get('CART_TEST_REDIS_URL'), 'Requires an explicit disposable Redis fixture URL')
class LoginCartRedisTests(LoginCartFixture, TestCase):
    def setUp(self):
        super().setUp()
        self.redis = Redis.from_url(os.environ['CART_TEST_REDIS_URL'])
        self.key = 'carts_'+self.buyer.username
        self.operation = str(uuid.uuid4())
        self.addCleanup(self.redis.close)
        self.addCleanup(self.redis.delete, self.key, receipt_key(self.buyer.username, self.operation))

    def test_missing_hash_returns_zero(self):
        self.assert_success(self.login(self.redis), 0)

    def test_atomic_cart_with_different_quantities_counts_only_sku_fields(self):
        items = [{'sku_id':str(sku), 'count':count, 'available_stock':100}
                 for sku, count in ((11, 2), (22, 7), (33, 13))]
        added = add_items(self.redis, self.buyer.username, self.operation, request_hash(items), items)
        self.assertEqual(added['data']['carts_count'], 3)
        before = self.redis.hgetall(self.key)
        self.assert_success(self.login(self.redis), 3)
        self.assertEqual(self.redis.hgetall(self.key), before)
        row = json.loads(self.redis.hget(self.key, '11'))
        row['count'] = 99
        self.redis.hset(self.key, '11', json.dumps(row))
        self.assert_success(self.login(self.redis), 3)

    def test_string_key_is_left_untouched_and_login_still_succeeds(self):
        self.redis.set(self.key, 'synthetic invalid cart')
        self.assert_success(self.login(self.redis), 0)
        self.assertEqual(self.redis.get(self.key), b'synthetic invalid cart')
