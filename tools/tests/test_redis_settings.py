"""Redis configuration checks without connecting to any database or Redis instance."""
import os
from pathlib import Path
import runpy
import unittest
from unittest.mock import patch

from dotenv import dotenv_values
from django_redis.pool import ConnectionFactory


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_ENV = {key: value or '' for key, value in dotenv_values(ROOT / '.env.example').items()}


class RedisSettingsTests(unittest.TestCase):
    def config(self, **values):
        with patch.dict(os.environ, EXAMPLE_ENV, clear=True):
            for name in ['REDIS_CACHE_URL', 'REDIS_CARTS_URL', 'REDIS_PASSWORD']:
                os.environ.pop(name, None)
            os.environ.update(values)
            with patch('dotenv.load_dotenv', return_value=False):
                return runpy.run_path(str(ROOT / 'tea_saas/settings.py'))['CACHES']

    def test_defaults_keep_separate_databases_without_authentication(self):
        caches = self.config()
        self.assertEqual(caches['default']['LOCATION'], 'redis://127.0.0.1:6379/0')
        self.assertEqual(caches['carts']['LOCATION'], 'redis://127.0.0.1:6379/1')
        for entry in caches.values():
            self.assertIsNone(entry['OPTIONS']['PASSWORD'])

    def test_password_reaches_both_clients_without_url_encoding(self):
        password = "synthetic-only:#@/'%"
        caches = self.config(REDIS_PASSWORD=password)
        for entry in caches.values():
            params = ConnectionFactory(entry['OPTIONS']).make_connection_params(entry['LOCATION'])
            self.assertEqual(params['password'], password)

    def test_independent_endpoints_and_empty_shared_password(self):
        caches = self.config(
            REDIS_CACHE_URL='redis://cache.example.invalid:6380/4',
            REDIS_CARTS_URL='rediss://cart-user:synthetic@cart.example.invalid:6381/5',
            REDIS_PASSWORD='',
        )
        self.assertEqual(caches['default']['LOCATION'], 'redis://cache.example.invalid:6380/4')
        self.assertEqual(caches['carts']['LOCATION'], 'rediss://cart-user:synthetic@cart.example.invalid:6381/5')
        for entry in caches.values():
            self.assertIsNone(entry['OPTIONS']['PASSWORD'])


if __name__ == '__main__':
    unittest.main()
