"""Account case semantics must survive the former MySQL CI collation."""
from unittest.mock import patch
from unittest import skipUnless
from django.db import connection
from django.db import IntegrityError, transaction
from django.test import TestCase
from tea_saas.utils import md5
from users.models import UserProfile


class IdentityCaseTests(TestCase):
    def setUp(self):
        UserProfile.objects.create(username='PgCaseUser',password=md5('fixture1'),is_active=True)

    def test_case_insensitive_login_returns_the_canonical_cart_identity(self):
        with patch('users.views.get_redis_connection'):
            result=self.client.post('/v1/users/login',{'username':'PGCASEUSER','password':'fixture1'},content_type='application/json').json()
        self.assertEqual(result['code'],200)
        self.assertEqual(result['username'],'PgCaseUser')

    def test_registration_rejects_a_case_variant(self):
        result=self.client.post('/v1/users/register',{'uname':'pgcaseuser','password':'fixture2',
            'phone':'00000000000','email':'synthetic@example.invalid'},content_type='application/json').json()
        self.assertEqual(result['code'],10002)

    def test_database_constraint_blocks_concurrent_case_variants(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProfile.objects.create(username='pgcaseuser')

    @skipUnless(connection.vendor == 'postgresql', 'requires PostgreSQL Unicode case conversion')
    def test_unicode_username_constraint_matches_authentication_normalization(self):
        UserProfile.objects.create(username='abcdeσ', password=md5('fixture1'), is_active=True)
        with self.assertRaises(IntegrityError), transaction.atomic():
            UserProfile.objects.create(username='abcdeς', password=md5('fixture1'), is_active=True)
