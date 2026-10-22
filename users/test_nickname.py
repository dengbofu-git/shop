"""Editable display names never replace authenticated login identities."""
import json
from django.test import TestCase
from tea_saas.utils import jwt_encode
from users.models import UserProfile, Role, UserRole


class NicknameTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.buyer = UserProfile.objects.create(username='nickbuyer',is_active=True,email='',phone='')
        cls.other = UserProfile.objects.create(username='nickother',is_active=True,email='',phone='')
        cls.merchant = UserProfile.objects.create(username='nickshop',user_type='merchant',shop_name='店铺名称',is_active=True)

    def headers(self, user, bearer=True):
        token=jwt_encode({'id':user.pk,'username':user.username})
        if isinstance(token,bytes):token=token.decode()
        return {'HTTP_AUTHORIZATION':('Bearer ' if bearer else '')+token}

    def save(self,user,value,**extra):
        return self.client.patch('/v1/users/%s/profile'%user.username,
            json.dumps({'nickname':value,**extra}),content_type='application/json',**self.headers(user))

    def test_edit_without_contact_info_and_read_back_without_changing_account(self):
        original=(self.buyer.username,self.buyer.password,self.buyer.user_type,self.buyer.email,self.buyer.phone)
        response=self.save(self.buyer,'  茶友🍃  ')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json()['data']['nickname'],'茶友🍃')
        self.assertIn('no-store',response['Cache-Control'])
        data=self.client.get('/v1/users/%s/profile'%self.buyer.username,**self.headers(self.buyer,bearer=False)).json()['data']
        self.assertEqual(data['nickname'],'茶友🍃')
        self.buyer.refresh_from_db()
        self.assertEqual((self.buyer.username,self.buyer.password,self.buyer.user_type,self.buyer.email,self.buyer.phone),original)

    def test_names_may_repeat_and_can_be_changed_or_cleared(self):
        for user in (self.buyer,self.other):self.assertEqual(self.save(user,'同一个昵称').status_code,200)
        self.assertEqual(self.save(self.buyer,'改过的昵称').status_code,200)
        self.assertEqual(self.save(self.buyer,'   ').json()['data']['nickname'],'')
        self.other.refresh_from_db()
        self.assertEqual(self.other.nickname,'同一个昵称')

    def test_unicode_limit_supports_thirty_emoji_and_rejects_long_or_control_names(self):
        self.assertEqual(self.save(self.buyer,'🍵'*30).status_code,200)
        for value in ('茶'*31,'🍵'*31,'茶\n友','茶\x00友',123,None,['昵称']):
            with self.subTest(value=value):self.assertEqual(self.save(self.buyer,value).status_code,400)
        self.buyer.refresh_from_db()
        self.assertEqual(self.buyer.nickname,'🍵'*30)

    def test_html_like_names_are_preserved_as_text(self):
        name='<img src=x onerror=alert(1)>'
        self.assertEqual(self.save(self.buyer,name).json()['data']['nickname'],name)

    def test_self_only_active_auth_and_no_identity_or_role_fields(self):
        self.assertEqual(self.client.patch('/v1/users/nickbuyer/profile',{'nickname':'x'},content_type='application/json').status_code,401)
        self.assertEqual(self.client.patch('/v1/users/nickother/profile',{'nickname':'x'},content_type='application/json',**self.headers(self.buyer)).status_code,403)
        for extra in ({'username':'operator'},{'user_type':'merchant'},{'shop_name':'wrong'},{'email':'other@example.test'}):
            self.assertEqual(self.save(self.buyer,'昵称',**extra).status_code,400)
        self.buyer.is_active=False;self.buyer.save()
        self.assertEqual(self.save(self.buyer,'昵称').status_code,401)

    def test_invalid_json_or_missing_field_leaves_original_value(self):
        for data in ('{bad','[]','{}','{"nickname":true}'):
            response=self.client.patch('/v1/users/nickbuyer/profile',data,content_type='application/json',**self.headers(self.buyer))
            self.assertEqual(response.status_code,400)
        self.buyer.refresh_from_db();self.assertEqual(self.buyer.nickname,'')

    def test_merchant_cannot_edit_nickname_and_profile_returns_current_store_name(self):
        self.merchant.nickname='历史商家昵称'
        self.merchant.save()
        self.assertEqual(self.save(self.merchant,'商家个人昵称').status_code,403)
        self.merchant.refresh_from_db()
        self.assertEqual(self.merchant.nickname,'历史商家昵称')
        self.assertEqual(self.merchant.shop_name,'店铺名称')
        data=self.client.get('/v1/users/%s/profile'%self.merchant.username,**self.headers(self.merchant,bearer=False)).json()['data']
        self.assertEqual(data['shop_name'],'店铺名称')

    def test_supplier_role_cannot_use_buyer_nickname_endpoint(self):
        supplier=Role.objects.create(code='supplier',name='商家',is_active=True)
        UserRole.objects.create(user_profile=self.other,role=supplier)
        self.assertEqual(self.save(self.other,'绕过角色的昵称').status_code,403)
        self.other.refresh_from_db()
        self.assertEqual(self.other.nickname,'')

    def test_legacy_contact_info_save_preserves_nickname(self):
        self.save(self.buyer,'昵称')
        response=self.client.put('/v1/users/nickbuyer/profile',{'email':'nick@example.test','phone':'13800000009'},
            content_type='application/json',**self.headers(self.buyer,bearer=False))
        self.assertEqual(response.json()['code'],200)
        self.buyer.refresh_from_db();self.assertEqual(self.buyer.nickname,'昵称')
