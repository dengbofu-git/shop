from django.test import TestCase
from users.models import UserProfile
from goods.models import Catalog,SPU
from goods.product_import_service import _existing_conflicts


class ImportNameCaseTests(TestCase):
    def test_same_shop_case_variant_is_an_existing_product(self):
        merchant=UserProfile.objects.create(username='pgnamecase',user_type='merchant',is_active=True)
        SPU.objects.create(name='Case Tea',merchant=merchant,catalog=Catalog.objects.create(name='绿茶'))
        rows=[{'data':{'name':'case tea'},'errors':[]}]
        self.assertTrue(_existing_conflicts(merchant,rows)[0]['errors'])
