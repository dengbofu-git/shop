"""Synthetic purchase-profile regressions; no model calls or business database."""
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch
import uuid

from django.test import TestCase, override_settings

from ai_storage.models import BuyerMemory
from goods.models import Brand, Catalog, SKU, SPU
from orders.models import CheckoutRequest, OrderGoods, OrderInfo, PreSaleOrder, TrialOrder
from users.models import UserProfile

from .profile_behavior import (BehaviorSnapshotLimit, build_behavior_snapshot,
                               reconcile_behavior_batch)


@override_settings(SUPPORT_AUTO_PROFILE_ENABLED=True, AI_STORAGE_DB_ALIAS='default')
class PurchaseProfileBehaviorTests(TestCase):
    databases = {'default'}

    def setUp(self):
        self.now = datetime(2026, 11, 11, 12, tzinfo=dt_timezone.utc)
        self.buyer = UserProfile.objects.create(username='pf-buyer', is_active=True)
        self.other = UserProfile.objects.create(username='pf-other', is_active=True)
        self.merchant = UserProfile.objects.create(username='pf-merchant', user_type='merchant', is_active=True)
        self.category = Catalog.objects.create(name='红茶')
        self.brand = Brand.objects.create(name='青山', first_letter='Q')
        self.product = SPU.objects.create(name='山香茶', catalog=self.category, brand=self.brand, merchant=self.merchant)
        self.sku = SKU.objects.create(name='合成规格', spu=self.product, price='100.00', market_price='100.00',
                                      cost_price='20.00', stock=10000, is_launched=True)
        self.sequence = 0

    def checkout(self, buyer=None):
        return CheckoutRequest.objects.create(user=buyer or self.buyer, request_id=uuid.uuid4().hex,
                                               fingerprint='a'*64)

    def purchase(self, *, days=0, hours=0, checkout=None, buyer=None, sku=None, count=1,
                 price='100.00', order_type='standard', status=None, paid=True, currency='CNY',
                 payment_exception='', deposit_paid=True, balance_paid=True):
        self.sequence += 1
        at = self.now-timedelta(days=days, hours=hours)
        total = Decimal(price)*count
        order = OrderInfo.objects.create(user_profile=buyer or self.buyer,
            order_id='profile-order-'+str(self.sequence), order_type=order_type,
            total_amount=total, total_count=count, freight='0.00',
            currency=currency, status=(4 if status is None else status) if order_type=='standard' else None,
            paid_at=at if paid else None, checkout_request=checkout,
            payment_exception=payment_exception, receiver='合成', address='合成地址',
            receiver_mobile='13000000000', tag='合成')
        if order_type=='trial':
            TrialOrder.objects.create(order_info=order, status=8 if status is None else status)
        if order_type=='presale':
            PreSaleOrder.objects.create(order_info=order, status=6 if status is None else status,
                deposit_amount='20.00', balance_amount=total-Decimal('20.00'),
                deposit_paid=deposit_paid, balance_paid=balance_paid,
                balance_pay_time=at if paid else None)
        OrderGoods.objects.create(order_info=order, sku=sku or self.sku, price=price, count=count, currency=currency)
        return order

    def snapshot(self, now=None):
        return build_behavior_snapshot(self.buyer.pk, now=now or self.now)

    def category_signal(self, snapshot=None):
        return next(c for c in (snapshot or self.snapshot())['candidates'] if c['type']=='category')

    @override_settings(SUPPORT_AUTO_PROFILE_ENABLED=False)
    def test_default_disabled_never_queries_or_enqueues(self):
        with self.assertNumQueries(0):
            snapshot = self.snapshot()
            swept = reconcile_behavior_batch(now=self.now)
        self.assertIsNone(snapshot['fingerprint'])
        self.assertEqual(snapshot['candidates'], [])
        self.assertEqual(swept['queued'], 0)
        self.assertTrue(swept['disabled'])

    def test_split_shops_and_bulk_quantity_are_only_one_purchase(self):
        checkout = self.checkout()
        self.purchase(checkout=checkout, count=99)
        second = self.purchase(checkout=checkout, count=50)
        # Both current shop ownership and quantity remain irrelevant to frequency.
        merchant = UserProfile.objects.create(username='pf-shop-two', is_active=True, user_type='merchant')
        second_item = second.ordergoods_set.get()
        second_item.merchant_snapshot = merchant
        second_item.save(update_fields=['merchant_snapshot'])
        signal = self.category_signal()
        self.assertEqual(signal['evidence']['group_count'], 1)
        self.assertEqual(signal['weight'], .35)
        self.assertEqual(signal['evidence']['reason'], 'single_large_purchase_weak')
        self.assertEqual(signal['evidence']['merchandise_cny'], '14900.00')
        self.assertNotIn('quote', signal)
        self.assertEqual(signal['polarity'], 'like')

    def test_three_distinct_groups_spanning_two_weeks_are_strong(self):
        for days in (30, 14, 1):
            self.purchase(checkout=self.checkout(), days=days)
        signal = self.category_signal()
        self.assertEqual(signal['evidence']['group_count'], 3)
        self.assertEqual(signal['evidence']['span_days'], 29)
        self.assertEqual(signal['weight'], 3.0)
        self.assertEqual(signal['source_at'], (self.now-timedelta(days=1)).isoformat())

    def test_two_purchases_one_to_thirty_days_apart_are_medium(self):
        self.purchase(checkout=self.checkout(), days=3)
        self.purchase(checkout=self.checkout(), days=1)
        signal = self.category_signal()
        self.assertEqual(signal['weight'], 1.25)
        self.assertEqual(signal['evidence']['reason'], 'short_interval_repeat')

    def test_near_simultaneous_checkouts_do_not_fake_short_interval_repeat(self):
        self.purchase(checkout=self.checkout(), hours=2)
        self.purchase(checkout=self.checkout(), hours=1)
        signal = self.category_signal()
        self.assertEqual(signal['weight'], .7)
        self.assertEqual(signal['evidence']['reason'], 'multiple_purchase_groups')

    def test_legacy_rows_share_a_local_payment_day(self):
        self.purchase(days=3, hours=1)
        self.purchase(days=3, hours=2)
        self.purchase(days=1)
        signal = self.category_signal()
        self.assertEqual(signal['evidence']['group_count'], 2)
        self.assertEqual(signal['weight'], 1.25)

    def test_only_completed_fully_paid_supported_states_contribute(self):
        expected = [self.purchase(checkout=self.checkout(), order_type='trial'),
                    self.purchase(checkout=self.checkout(), order_type='presale')]
        # A recorded presale balance payment is also a reliable payment source.
        OrderInfo.objects.filter(pk=expected[1].pk).update(paid_at=None)
        self.purchase(status=1, paid=False)
        self.purchase(status=2)
        self.purchase(status=4, paid=False)
        self.purchase(order_type='trial', status=7)
        self.purchase(order_type='trial', status=6)
        self.purchase(order_type='presale', status=7)
        self.purchase(order_type='presale', balance_paid=False)
        self.purchase(currency='USD')
        self.purchase(payment_exception='late_payment_refund_required')
        self.purchase(days=181)
        self.purchase(days=-1)
        snapshot = self.snapshot()
        self.assertEqual(set(snapshot['evidence']['orders']), {o.pk for o in expected})
        self.assertEqual(self.category_signal(snapshot)['evidence']['group_count'], 2)

    def test_invalid_or_free_lines_do_not_become_purchase_signals(self):
        self.purchase(price='0.00')
        zero_count = self.purchase()
        zero_count.ordergoods_set.update(count=0)
        foreign_line = self.purchase()
        foreign_line.ordergoods_set.update(currency='USD')
        snapshot = self.snapshot()
        self.assertEqual(snapshot['candidates'], [])
        self.assertIsNone(snapshot['source_at'])

    def test_other_account_never_enters_snapshot(self):
        category = Catalog.objects.create(name='白茶')
        product = SPU.objects.create(name='他人茶', catalog=category, merchant=self.merchant)
        sku = SKU.objects.create(name='合成规格', spu=product, price='100.00', market_price='100.00',
                                 cost_price='20.00', stock=100, is_launched=True)
        self.purchase(buyer=self.other, checkout=self.checkout(self.other), sku=sku)
        self.purchase(checkout=self.checkout())
        self.assertNotIn('白茶', [c['value'] for c in self.snapshot()['candidates']])
        self.assertTrue(all(c['value']!='他人茶' for c in self.snapshot()['candidates']))

    def test_forged_checkout_owner_is_not_an_independent_purchase(self):
        self.purchase(checkout=self.checkout(self.other))
        snapshot = self.snapshot()
        self.assertEqual(snapshot['candidates'], [])
        self.assertEqual(snapshot['evidence']['rejected']['checkout_owner_mismatch'], 1)

    def test_polling_time_is_not_fingerprint_or_purchase_time(self):
        order = self.purchase(checkout=self.checkout(), days=1)
        first = self.snapshot()
        later = self.snapshot(now=self.now+timedelta(hours=1))
        self.assertEqual(first['fingerprint'], later['fingerprint'])
        self.assertEqual(first['source_at'], order.paid_at)
        self.assertEqual(first['source_at'], later['source_at'])
        self.assertNotEqual(first['evidence']['observed_at'], later['evidence']['observed_at'])

    def test_bulk_cancellation_and_refund_clear_old_behavior_snapshot(self):
        standard = self.purchase(checkout=self.checkout())
        trial = self.purchase(checkout=self.checkout(), order_type='trial')
        first = self.snapshot()
        # Deliberately bypass model.save/signals and updated_time.
        OrderInfo.objects.filter(pk=standard.pk).update(status=0)
        TrialOrder.objects.filter(order_info=trial).update(status=7)
        cleared = self.snapshot()
        self.assertNotEqual(first['fingerprint'], cleared['fingerprint'])
        self.assertEqual(cleared['candidates'], [])
        self.assertIsNone(cleared['source_at'])
        self.assertEqual(cleared['evidence']['purchase_groups'], [])
        # A->B->A is intentionally the same content hash; queue generation, not
        # a permanent hash-only event key, must distinguish this transition.
        OrderInfo.objects.filter(pk=standard.pk).update(status=4)
        TrialOrder.objects.filter(order_info=trial).update(status=8)
        self.assertEqual(first['fingerprint'], self.snapshot()['fingerprint'])

    def test_window_expiry_invalidates_without_order_update(self):
        self.purchase(days=179)
        first = self.snapshot()
        expired = self.snapshot(now=self.now+timedelta(days=2))
        self.assertTrue(first['candidates'])
        self.assertEqual(expired['candidates'], [])
        self.assertIsNone(expired['source_at'])

    def test_term_time_cannot_borrow_later_payment_from_another_shop(self):
        checkout = self.checkout()
        old = self.purchase(checkout=checkout, days=10)
        category = Catalog.objects.create(name='绿茶')
        product = SPU.objects.create(name='春香茶', catalog=category, merchant=self.merchant)
        sku = SKU.objects.create(name='合成规格', spu=product, price='100.00', market_price='100.00',
                                 cost_price='20.00', stock=100, is_launched=True)
        self.purchase(checkout=checkout, sku=sku)
        snapshot = self.snapshot()
        red = next(c for c in snapshot['candidates'] if c['type']=='category' and c['value']=='红茶')
        self.assertEqual(red['source_at'], old.paid_at.isoformat())
        self.assertEqual(snapshot['source_at'], self.now)

    def test_private_product_terms_are_rejected_not_sent_to_a_model(self):
        self.brand.name = 'test@example.com'
        self.brand.save(update_fields=['name'])
        self.product.name = '联系电话13812345678'
        self.product.save(update_fields=['name'])
        self.purchase()
        snapshot = self.snapshot()
        self.assertEqual({c['type'] for c in snapshot['candidates']}, {'category'})
        self.assertTrue(all('quote' not in c for c in snapshot['candidates']))

    def test_snapshot_limit_raises_instead_of_applying_partial_history(self):
        self.purchase(checkout=self.checkout(), days=2)
        self.purchase(checkout=self.checkout(), days=1)
        with patch('support_ai.profile_behavior.MAX_ORDERS', 1):
            with self.assertRaises(BehaviorSnapshotLimit):
                self.snapshot()

    def test_sweep_is_paged_and_keeps_owners_without_eligible_orders(self):
        self.purchase(checkout=self.checkout())
        BuyerMemory.objects.create(owner_id=self.other.pk, preferences={})
        calls = []
        def capture(owner_id, fingerprint, source_at, candidates, evidence=None):
            calls.append((owner_id, candidates))
            return object()
        with patch('ai_storage.profile_service.enqueue_behavior', side_effect=capture):
            first = reconcile_behavior_batch(limit=1, now=self.now)
            second = reconcile_behavior_batch(after_owner_id=first['cursor'], limit=1, now=self.now)
        self.assertFalse(first['complete'])
        self.assertTrue(second['complete'])
        self.assertEqual(first['queued']+second['queued'], 2)
        self.assertEqual([owner_id for owner_id,_ in calls], [self.buyer.pk,self.other.pk])
        self.assertEqual(calls[1][1], [])

    def test_sweep_skips_inactive_accounts_and_reports_bound_failures(self):
        self.purchase(checkout=self.checkout())
        self.other.is_active = False
        self.other.save(update_fields=['is_active'])
        BuyerMemory.objects.create(owner_id=self.other.pk, preferences={})
        with patch('support_ai.profile_behavior.build_behavior_snapshot', side_effect=BehaviorSnapshotLimit('bounded')):
            with patch('ai_storage.profile_service.enqueue_behavior') as enqueue:
                result = reconcile_behavior_batch(now=self.now)
        enqueue.assert_not_called()
        self.assertEqual(result['processed'], 0)
        self.assertEqual({r['code'] for r in result['skipped']}, {'snapshot_limit','inactive_or_non_buyer'})

    def test_sweep_idempotence_and_state_reversion_use_queue_generations(self):
        from ai_storage.profile_models import PreferenceUpdateJob
        order = self.purchase(checkout=self.checkout())
        first = reconcile_behavior_batch(now=self.now)
        again = reconcile_behavior_batch(now=self.now+timedelta(minutes=1))
        self.assertEqual((first['queued'],again['queued']), (1,0))
        OrderInfo.objects.filter(pk=order.pk).update(status=0)
        cancelled = reconcile_behavior_batch(now=self.now+timedelta(minutes=2))
        OrderInfo.objects.filter(pk=order.pk).update(status=4)
        restored = reconcile_behavior_batch(now=self.now+timedelta(minutes=3))
        self.assertEqual((cancelled['queued'],restored['queued']), (1,1))
        self.assertEqual(PreferenceUpdateJob.objects.filter(owner_id=self.buyer.pk,source_type='behavior').count(), 3)

    def test_chat_only_job_does_not_enroll_account_in_purchase_reconciliation(self):
        from ai_storage.profile_models import BuyerPreferenceState, PreferenceUpdateJob
        from ai_storage.profile_service import enqueue_chat
        from support_ai.models import SupportConversation, SupportTurn
        conversation = SupportConversation.objects.create(user=self.buyer)
        turn = SupportTurn.objects.create(conversation=conversation, user=self.buyer,
            request_id=uuid.uuid4(), request_hash='synthetic-chat-only', sequence=1,
            user_text='我一直喜欢红茶', answer='合成回复', intent='question_answering', response={'tasks':[]})
        self.assertIsNotNone(enqueue_chat(turn))
        self.assertFalse(BuyerMemory.objects.exists())
        self.assertFalse(BuyerPreferenceState.objects.exists())
        result = reconcile_behavior_batch(now=self.now)
        self.assertEqual(result['processed'], 0)
        self.assertEqual(result['queued'], 0)
        self.assertTrue(result['complete'])
        self.assertEqual(PreferenceUpdateJob.objects.filter(source_type='chat').count(), 1)
        self.assertFalse(PreferenceUpdateJob.objects.filter(source_type='behavior').exists())
        self.assertFalse(BuyerPreferenceState.objects.exists())
