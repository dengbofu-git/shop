"""Both conversation list and history use a buyer's current display nickname."""
from django.test import TestCase
from users.models import UserProfile
from .models import Conversation,Message
from . import tests as fixtures


class ConversationNicknameTests(TestCase):
    make_sku=staticmethod(fixtures.EngagementTests.make_sku)
    @classmethod
    def setUpTestData(cls):
        fixtures.EngagementTests.setUpTestData.__func__(cls)

    call=fixtures.EngagementTests.call
    send=fixtures.EngagementTests.send

    def test_saved_nickname_updates_list_and_history_without_rewriting_messages(self):
        conv=self.send(request='nickname-original').json()['data']['conversation_id']
        original=list(Message.objects.values('pk','text','sender_id','conversation_id','context','created_at'))
        for name in ('茶友阿青','换一个昵称',''):
            UserProfile.objects.filter(pk=self.buyer.pk).update(nickname=name)
            expected=name or self.buyer.username[:1]+'***'
            listing=self.call('conversations',self.shop).json()['data']['items']
            history=self.call('conversations/%s/messages'%conv,self.shop).json()['data']
            self.assertEqual(listing[0]['name'],expected)
            self.assertEqual(history['name'],expected)
            self.assertEqual(history['conversation_id'],conv)
        self.assertEqual(list(Message.objects.values('pk','text','sender_id','conversation_id','context','created_at')),original)

    def test_same_nickname_keeps_pair_ids_and_privacy_separate(self):
        UserProfile.objects.filter(pk__in=[self.buyer.pk,self.other.pk]).update(nickname='同名茶友')
        first=self.send(request='nickname-one').json()['data']['conversation_id']
        second=self.send(user=self.other,request='nickname-two').json()['data']['conversation_id']
        rows=self.call('conversations',self.shop).json()['data']['items']
        self.assertEqual({row['id'] for row in rows},{first,second})
        self.assertEqual([row['name'] for row in rows],['同名茶友','同名茶友'])
        self.assertEqual(self.call('conversations/%s/messages'%first,self.other).status_code,404)

    def test_buyer_still_sees_store_name_and_nickname_is_not_account_data(self):
        self.shop.nickname='商家个人名';self.shop.save()
        self.buyer.nickname='<img src=x onerror=alert(1)>';self.buyer.save()
        conv=self.send(request='nickname-html').json()['data']['conversation_id']
        self.assertEqual(self.call('conversations/%s/messages'%conv,self.buyer).json()['data']['name'],self.shop.shop_name)
        row=self.call('conversations',self.shop).json()['data']['items'][0]
        self.assertEqual(row['name'],self.buyer.nickname)
        self.assertNotIn('username',row)
        self.assertNotIn('email',row)
        self.assertNotIn('phone',row)
