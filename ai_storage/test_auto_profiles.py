"""Synthetic account profile/outbox regressions on the isolated unified database."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
import uuid
from unittest.mock import patch

from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, connections, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from users.models import UserProfile
from support_ai.models import SupportConversation, SupportTurn
from .models import BuyerMemory, BuyerPreferenceState, PreferenceAudit, PreferenceUpdateJob
from . import profile_service as service


def candidate(value='乌龙茶', polarity='like', quote='我一直喜欢乌龙茶', **kwargs):
    result=dict(type='category',value=value,polarity=polarity,scope='long_term',quote=quote)
    result.update(kwargs)
    return result


def behavior(value='乌龙茶', at=None, weight=1):
    return dict(type='category',value=value,polarity='like',scope='long_term',weight=weight,
                source_at=(at or timezone.now()).isoformat(),evidence={'independent_groups':3})


@override_settings(SUPPORT_AUTO_PROFILE_ENABLED=True, SUPPORT_PROFILE_CHAT_ENABLED=True,
                   SUPPORT_PROFILE_BEHAVIOR_ENABLED=True, AI_STORAGE_DB_ALIAS='default')
class AutoProfileTests(TestCase):
    def setUp(self):
        self.user=UserProfile.objects.create(username='prof-buyer',user_type='customer',is_active=True)
        self.other=UserProfile.objects.create(username='prof-other',user_type='customer',is_active=True)

    def turn(self, text='我一直喜欢乌龙茶', owner=None, at=None, response=None, pk=None):
        user=owner or self.user
        conv=SupportConversation.objects.create(user=user)
        row=SupportTurn.objects.create(pk=pk,user=user,conversation=conv,request_id=uuid.uuid4(),request_hash='synthetic',
            sequence=1,user_text=text,answer='合成回复',intent='question_answering',
            response=response or {'intent':'question_answering','answer':'合成回复','tasks':[]})
        if at:
            SupportTurn.objects.filter(pk=row.pk).update(created_at=at)
            row.refresh_from_db()
        return row

    def apply_chat(self, turn, values=None, **kwargs):
        return service.apply_candidates(self.user.pk,values or [candidate(quote=turn.user_text)],'chat',str(turn.pk),turn.created_at,**kwargs)

    def finish_behavior(self, items, marker='a', source_at=None):
        job=service.enqueue_behavior(self.user.pk,marker*64,source_at,items,evidence={})
        claimed=service.claim_job()
        self.assertEqual(claimed.pk,job.pk)
        return service.complete_job(claimed.pk,claimed.lease_token,items)

    def prefs(self):
        return service.read_preferences(self.user)['preferences']

    def test_legacy_three_fields_are_adopted_without_loss(self):
        old=BuyerMemory.objects.create(owner_id=self.user.pk,preferences={'categories':['红茶'],'brands':['合成品牌'],'keywords':[]})
        source=self.turn(at=old.updated_at-timedelta(seconds=2),text='我一直喜欢绿茶')
        result=self.apply_chat(source,[candidate('绿茶',quote=source.user_text)])
        self.assertEqual(result['applied'],0)
        self.assertIn('before_manual_field_update',result['reasons'])
        self.assertEqual(self.prefs()['categories'],['红茶'])
        self.assertEqual(self.prefs()['brands'],['合成品牌'])

    def test_quote_and_owner_checks_do_not_trust_candidate_source(self):
        turn=self.turn()
        result=self.apply_chat(turn,[candidate(quote='原文里没有这句话')])
        self.assertEqual(result['rejected'],1)
        foreign=self.turn(owner=self.other)
        result=service.apply_candidates(self.user.pk,[candidate()],'chat',str(foreign.pk),foreign.created_at)
        self.assertIn('chat_source_unavailable',result['reasons'])
        self.assertIsNone(service.read_preferences(self.user))

    def test_legacy_bootstrap_survives_deleted_chat_source(self):
        BuyerMemory.objects.create(owner_id=self.user.pk,preferences={
            'categories':['红茶'],'brands':['合成品牌'],'keywords':['春茶']})
        turn=self.turn()
        service.enqueue_chat(turn)
        turn.delete()
        job=service.claim_job()
        result=service.complete_job(job.pk,job.lease_token,[])
        self.assertIn('chat_source_unavailable',result['reasons'])
        values=self.prefs()
        self.assertEqual(values['categories'],['红茶'])
        self.assertEqual(values['brands'],['合成品牌'])
        self.assertEqual(values['keywords'],['春茶'])
        self.assertTrue(BuyerPreferenceState.objects.get().records)

    def test_legacy_projection_survives_pending_behavior_job(self):
        BuyerMemory.objects.create(owner_id=self.user.pk,preferences={'categories':['红茶'],'brands':[],'keywords':[]})
        service.enqueue_behavior(self.user.pk,'f'*64,timezone.now(),[behavior()])
        self.assertEqual(self.prefs()['categories'],['红茶'])
        self.assertEqual(PreferenceUpdateJob.objects.get().status,'queued')

    def test_legacy_projection_survives_stale_behavior_early_return(self):
        BuyerMemory.objects.create(owner_id=self.user.pk,preferences={'categories':['红茶'],'brands':[],'keywords':[]})
        result=service.apply_candidates(self.user.pk,[],'behavior','obsolete',None,behavior_generation=1)
        self.assertTrue(result['stale'])
        self.assertEqual(self.prefs()['categories'],['红茶'])

    def test_current_purchase_conditions_and_invalid_terms_are_rejected(self):
        turn=self.turn()
        values=[candidate(scope='current_turn')]
        # Use an explicit override rather than constructing duplicate keyword arguments.
        values[0]['scope']='current_turn'
        values.append(candidate(value='13800138000'))
        result=self.apply_chat(turn,values)
        self.assertEqual(result['rejected'],2)
        self.assertIsNone(service.read_preferences(self.user))

    def test_real_source_time_beats_late_worker_completion(self):
        earlier=timezone.now()-timedelta(days=1)
        old=self.turn(at=earlier)
        correction=self.turn(text='我现在一直不喜欢乌龙茶')
        self.apply_chat(correction,[candidate(polarity='hate',quote=correction.user_text)])
        self.apply_chat(old)
        self.assertEqual(self.prefs()['categories'],[])
        self.assertEqual(self.prefs()['disliked_categories'],['乌龙茶'])

    def test_forged_chat_timestamp_does_not_bypass_manual_reset(self):
        old=self.turn()
        service.manual_preferences(self.user,delete=True)
        result=service.apply_candidates(self.user.pk,[candidate()],'chat',str(old.pk),timezone.now()+timedelta(days=100))
        self.assertIn('before_manual_reset',result['reasons'])
        self.assertIsNone(service.read_preferences(self.user))

    def test_new_explicit_chat_can_correct_manual_choice(self):
        service.manual_preferences(self.user,{'categories':['乌龙茶']})
        turn=self.turn(text='我现在一直不喜欢乌龙茶')
        result=self.apply_chat(turn,[candidate(polarity='hate',quote=turn.user_text)])
        self.assertEqual(result['applied'],1)
        self.assertEqual(self.prefs()['disliked_categories'],['乌龙茶'])

    def test_manual_removed_term_is_not_restored_by_new_behavior(self):
        service.manual_preferences(self.user,{'categories':['乌龙茶']})
        service.manual_preferences(self.user,{'categories':[]})
        result=self.finish_behavior([behavior()],source_at=timezone.now())
        self.assertIn('explicit_preference_wins',result['reasons'])
        self.assertIsNone(service.read_preferences(self.user))

    def test_old_behavior_does_not_restore_a_new_unknown_key_after_reset(self):
        old=timezone.now()-timedelta(days=1)
        service.manual_preferences(self.user,delete=True)
        result=self.finish_behavior([behavior('红茶',old)],source_at=old)
        self.assertIn('before_manual_reset',result['reasons'])
        self.assertIsNone(service.read_preferences(self.user))

    def test_manual_partial_write_preserves_new_negative_fields(self):
        service.manual_preferences(self.user,{'disliked_categories':['红茶']})
        values=service.manual_preferences(self.user,{'categories':['绿茶'],'brands':[],'keywords':[]})
        self.assertEqual(values['disliked_categories'],['红茶'])

    def test_manual_field_replacement_blocks_unknown_late_chat_term(self):
        old=self.turn(text='我一直喜欢红茶')
        service.enqueue_chat(old)
        service.manual_preferences(self.user,{'categories':['绿茶']})
        job=service.claim_job()
        result=service.complete_job(job.pk,job.lease_token,[candidate('红茶',quote=old.user_text)])
        self.assertIn('before_manual_field_update',result['reasons'])
        self.assertEqual(self.prefs()['categories'],['绿茶'])

    def test_empty_manual_field_blocks_unknown_old_behavior(self):
        old=timezone.now()-timedelta(days=1)
        service.manual_preferences(self.user,{'categories':[]})
        result=self.finish_behavior([behavior('红茶',old)],source_at=old)
        self.assertIn('before_manual_field_update',result['reasons'])
        self.assertIsNone(service.read_preferences(self.user))

    def test_field_fence_does_not_affect_unsubmitted_type_or_polarity(self):
        before=timezone.now()-timedelta(seconds=1)
        brand=self.turn(text='我一直喜欢合成品牌',at=before)
        hate=self.turn(text='我一直不喜欢红茶',at=before)
        service.manual_preferences(self.user,{'categories':['绿茶']})
        self.apply_chat(brand,[dict(type='brand',value='合成品牌',polarity='like',scope='long_term',quote=brand.user_text)])
        self.apply_chat(hate,[candidate('红茶',polarity='hate',quote=hate.user_text)])
        values=self.prefs()
        self.assertEqual(values['categories'],['绿茶'])
        self.assertEqual(values['brands'],['合成品牌'])
        self.assertEqual(values['disliked_categories'],['红茶'])

    def test_newer_chat_can_add_term_after_explicit_field_replacement(self):
        service.manual_preferences(self.user,{'categories':['绿茶']})
        source=self.turn(text='我一直喜欢红茶')
        result=self.apply_chat(source,[candidate('红茶',quote=source.user_text)])
        self.assertEqual(result['applied'],1)
        self.assertEqual(set(self.prefs()['categories']),{'绿茶','红茶'})

    def test_same_time_chat_turn_pk_is_ordered_numerically(self):
        at=timezone.now()-timedelta(seconds=1)
        earlier=self.turn(pk=9,at=at)
        later=self.turn(pk=10,at=at,text='我一直不喜欢乌龙茶')
        self.apply_chat(later,[candidate(polarity='hate',quote=later.user_text)])
        result=self.apply_chat(earlier)
        self.assertIn('older_or_duplicate_explicit_source',result['reasons'])
        self.assertEqual(self.prefs()['categories'],[])
        self.assertEqual(self.prefs()['disliked_categories'],['乌龙茶'])

    def test_manual_edit_wins_same_timestamp_as_opposite_chat(self):
        at=timezone.now()-timedelta(seconds=1)
        with patch.object(service.timezone,'now',return_value=at):
            service.manual_preferences(self.user,{'categories':['乌龙茶']})
        source=self.turn(at=at,text='我一直不喜欢乌龙茶')
        result=self.apply_chat(source,[candidate(polarity='hate',quote=source.user_text)])
        self.assertIn('older_or_duplicate_explicit_source',result['reasons'])
        self.assertEqual(self.prefs()['categories'],['乌龙茶'])

    def test_same_manual_request_cannot_like_and_hate_one_term(self):
        with self.assertRaisesRegex(ValueError,'polarity_conflict'):
            service.manual_preferences(self.user,{'categories':['乌龙茶'],'disliked_categories':['乌龙茶']})
        self.assertFalse(BuyerPreferenceState.objects.exists())

    def test_conflicting_extracted_batch_does_not_guess_a_polarity(self):
        turn=self.turn(text='我以前喜欢乌龙茶现在不喜欢乌龙茶')
        result=self.apply_chat(turn,[candidate(quote=turn.user_text),candidate(polarity='hate',quote=turn.user_text)])
        self.assertEqual(result['ignored'],2)
        self.assertIsNone(service.read_preferences(self.user))

    def test_normalization_and_repeated_extraction_do_not_accumulate(self):
        turn=self.turn(text='I always like ACME')
        item=dict(type='brand',value='ＡＣＭＥ',polarity='like',scope='long_term',quote=turn.user_text)
        self.apply_chat(turn,[item,item])
        self.apply_chat(turn,[item])
        self.assertEqual(self.prefs()['brands'],['ACME'])
        self.assertEqual(len(BuyerPreferenceState.objects.get().records),1)

    def test_behavior_is_weak_and_decays_without_changing_explicit_facts(self):
        at=timezone.now()-timedelta(days=30)
        self.finish_behavior([behavior(at=at)],source_at=at)
        self.assertEqual(self.prefs()['categories'],['乌龙茶'])
        later=service.read_preferences(self.user,now=timezone.now()+timedelta(days=180))
        self.assertIsNone(later)
        service.manual_preferences(self.user,{'categories':['乌龙茶']})
        self.assertEqual(service.read_preferences(self.user,now=timezone.now()+timedelta(days=500))['preferences']['categories'],['乌龙茶'])

    def test_single_large_purchase_signal_cannot_become_strong_preference(self):
        self.finish_behavior([behavior(weight=.35)],source_at=timezone.now())
        self.assertIsNone(service.read_preferences(self.user))
        self.assertTrue(BuyerPreferenceState.objects.get().records)

    def test_deleted_projection_is_not_recreated_by_late_job_or_empty_snapshot(self):
        service.manual_preferences(self.user,{'categories':['绿茶']})
        old=self.turn(text='我一直喜欢红茶')
        service.enqueue_chat(old)
        cleared=service.manual_preferences(self.user,delete=True)
        self.assertTrue(all(not values for values in cleared.values()))
        self.assertFalse(BuyerMemory.objects.filter(owner_id=self.user.pk).exists())
        state=BuyerPreferenceState.objects.get(owner_id=self.user.pk)
        self.assertIsNotNone(state.reset_at)
        self.assertTrue(state.records)
        job=service.claim_job()
        result=service.complete_job(job.pk,job.lease_token,[candidate('红茶',quote=old.user_text)])
        self.assertIn('before_manual_reset',result['reasons'])
        self.assertFalse(BuyerMemory.objects.filter(owner_id=self.user.pk).exists())
        self.assertIsNone(service.read_preferences(self.user))
        self.finish_behavior([],marker='f')
        self.assertFalse(BuyerMemory.objects.filter(owner_id=self.user.pk).exists())
        self.assertIsNone(service.read_preferences(self.user))
        self.assertTrue(BuyerPreferenceState.objects.filter(owner_id=self.user.pk).exists())

    def test_refund_empty_snapshot_only_clears_behavior(self):
        service.manual_preferences(self.user,{'brands':['合成品牌']})
        self.finish_behavior([behavior()],source_at=timezone.now())
        self.finish_behavior([],marker='b')
        self.assertEqual(self.prefs()['categories'],[])
        self.assertEqual(self.prefs()['brands'],['合成品牌'])

    def test_same_fingerprint_is_not_requeued_but_a_b_a_transition_is(self):
        at=timezone.now()
        first=service.enqueue_behavior(self.user.pk,'a'*64,at,[behavior(at=at)])
        self.assertIsNone(service.enqueue_behavior(self.user.pk,'a'*64,at,[behavior(at=at)]))
        service.enqueue_behavior(self.user.pk,'b'*64,None,[])
        third=service.enqueue_behavior(self.user.pk,'a'*64,at,[behavior(at=at)])
        self.assertNotEqual(first.pk,third.pk)
        self.assertEqual(PreferenceUpdateJob.objects.count(),3)
        job=service.claim_job()
        result=service.complete_job(job.pk,job.lease_token,job.payload['candidates'])
        self.assertTrue(result['stale'])
        job=service.claim_job()
        self.assertTrue(service.complete_job(job.pk,job.lease_token,job.payload['candidates'])['stale'])
        job=service.claim_job()
        service.complete_job(job.pk,job.lease_token,job.payload['candidates'])
        self.assertEqual(self.prefs()['categories'],['乌龙茶'])

    def test_outbox_is_atomic_and_repeated_turn_is_idempotent(self):
        turn=self.turn()
        self.assertEqual(service.enqueue_chat(turn).pk,service.enqueue_chat(turn).pk)
        self.assertEqual(PreferenceUpdateJob.objects.count(),1)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                other=self.turn(text='我一直喜欢绿茶')
                service.enqueue_chat(other)
                raise RuntimeError('synthetic rollback')
        self.assertEqual(PreferenceUpdateJob.objects.count(),1)

    def test_chat_admission_time_must_be_aware_and_not_after_commit(self):
        turn=self.turn()
        for at in [turn.created_at.replace(tzinfo=None),turn.created_at+timedelta(seconds=1),timezone.now()+timedelta(days=1)]:
            with self.subTest(at=at),self.assertRaises(ValueError):
                service.enqueue_chat(turn,source_at=at)
        self.assertFalse(PreferenceUpdateJob.objects.exists())

    def test_slow_earlier_request_does_not_override_later_correction(self):
        now=timezone.now()
        correction=self.turn(text='我现在不喜欢乌龙茶',at=now-timedelta(seconds=2))
        service.enqueue_chat(correction,source_at=now-timedelta(seconds=3))
        slow=self.turn(at=now-timedelta(seconds=1))
        service.enqueue_chat(slow,source_at=now-timedelta(seconds=5))
        job=service.claim_job()
        self.assertEqual(job.source_ref,str(correction.pk))
        service.complete_job(job.pk,job.lease_token,[candidate(polarity='hate',quote=correction.user_text)])
        job=service.claim_job()
        result=service.complete_job(job.pk,job.lease_token,[candidate()])
        self.assertIn('older_or_duplicate_explicit_source',result['reasons'])
        self.assertEqual(self.prefs()['disliked_categories'],['乌龙茶'])

    def test_newer_request_can_correct_slow_request_when_processed_after_it(self):
        now=timezone.now()
        slow=self.turn(at=now-timedelta(seconds=1))
        service.enqueue_chat(slow,source_at=now-timedelta(seconds=5))
        correction=self.turn(text='我现在不喜欢乌龙茶',at=now-timedelta(seconds=2))
        service.enqueue_chat(correction,source_at=now-timedelta(seconds=3))
        job=service.claim_job()
        service.complete_job(job.pk,job.lease_token,[candidate()])
        job=service.claim_job()
        service.complete_job(job.pk,job.lease_token,[candidate(polarity='hate',quote=correction.user_text)])
        self.assertEqual(self.prefs()['categories'],[])
        self.assertEqual(self.prefs()['disliked_categories'],['乌龙茶'])

    def test_manual_edit_during_slow_request_blocks_unknown_late_term(self):
        admission=timezone.now()-timedelta(seconds=1)
        service.manual_preferences(self.user,{'categories':['绿茶']})
        slow=self.turn(text='我一直喜欢红茶')
        service.enqueue_chat(slow,source_at=admission)
        job=service.claim_job()
        result=service.complete_job(job.pk,job.lease_token,[candidate('红茶',quote=slow.user_text)])
        self.assertIn('before_manual_field_update',result['reasons'])
        self.assertEqual(self.prefs()['categories'],['绿茶'])

    def test_caller_time_cannot_override_application_admission_event(self):
        admission=timezone.now()-timedelta(seconds=1)
        service.manual_preferences(self.user,{'categories':['绿茶']})
        slow=self.turn(text='我一直喜欢红茶')
        service.enqueue_chat(slow,source_at=admission)
        result=service.apply_candidates(self.user.pk,[candidate('红茶',quote=slow.user_text)],
            'chat',str(slow.pk),timezone.now()+timedelta(days=100))
        self.assertIn('before_manual_field_update',result['reasons'])
        self.assertEqual(self.prefs()['categories'],['绿茶'])

    def test_completion_revalidates_event_key_and_turn_owner_binding(self):
        turn=self.turn();service.enqueue_chat(turn);job=service.claim_job()
        PreferenceUpdateJob.objects.filter(pk=job.pk).update(event_key='chat:999999999')
        result=service.complete_job(job.pk,job.lease_token,[candidate()])
        self.assertEqual(result['reasons'],['chat_event_binding_invalid'])
        self.assertFalse(BuyerMemory.objects.exists())
        other_turn=self.turn(owner=self.other)
        service.enqueue_chat(other_turn)
        job=service.claim_job()
        PreferenceUpdateJob.objects.filter(pk=job.pk).update(owner_id=self.user.pk)
        result=service.complete_job(job.pk,job.lease_token,[candidate()])
        self.assertEqual(result['reasons'],['chat_event_binding_invalid'])
        self.assertFalse(BuyerMemory.objects.exists())

    def test_extraction_audit_only_stores_bounded_content_free_codes(self):
        turn=self.turn();service.enqueue_chat(turn);job=service.claim_job()
        audit=[{'index':1,'reason':'quote_not_verbatim'},{'index':0,'reason':'current_turn'}]
        result=service.complete_job(job.pk,job.lease_token,[],extraction_rejections=audit)
        expected=sorted(audit,key=lambda row:row['index'])
        self.assertEqual(result['extraction_rejections'],expected)
        job.refresh_from_db()
        self.assertEqual(job.results['extraction_rejections'],expected)

    def test_invalid_extraction_audit_never_persists_rejected_content(self):
        turn=self.turn();service.enqueue_chat(turn);job=service.claim_job()
        invalid=[
            [{'index':0,'reason':'arbitrary private text'}],
            [{'index':0,'reason':'current_turn','quote':'private text'}],
            [{'index':True,'reason':'current_turn'}],
            [{'index':6,'reason':'current_turn'}],
            [{'index':0,'reason':{'private':'content'}}],
            [{'index':0,'reason':'current_turn'}]*2,
            [{'index':0,'reason':'current_turn'}]*7,
        ]
        for audit in invalid:
            with self.subTest(audit=audit),self.assertRaisesRegex(ValueError,'extraction_audit_invalid'):
                service.complete_job(job.pk,job.lease_token,[],extraction_rejections=audit)
        job.refresh_from_db()
        self.assertEqual(job.results,{})
        self.assertEqual(job.status,'running')
        self.assertFalse(BuyerMemory.objects.exists())

    def test_failed_and_blocked_turns_never_queue(self):
        for response in [{'compliance_blocked':True},{'error':'synthetic'}, {'tasks':[{'status':'failed'}]},
                         {'completion_status':'partial'}, {'tasks':[{'status':'skipped'}]}]:
            turn=self.turn(response=response)
            self.assertIsNone(service.enqueue_chat(turn))
        self.assertEqual(PreferenceUpdateJob.objects.count(),0)

    def test_lost_lease_cannot_apply_and_new_lease_commits_exactly_once(self):
        turn=self.turn();service.enqueue_chat(turn)
        job=service.claim_job();token=job.lease_token
        replacement=service.claim_job(now=job.lease_until+timedelta(seconds=1))
        stale=service.complete_job(job.pk,token,[candidate()],now=job.lease_until+timedelta(seconds=2))
        self.assertTrue(stale['stale'])
        done=service.complete_job(replacement.pk,replacement.lease_token,[candidate()],now=job.lease_until+timedelta(seconds=2))
        self.assertEqual(done['applied'],1)
        revision=BuyerPreferenceState.objects.get().revision
        self.assertTrue(service.complete_job(replacement.pk,replacement.lease_token,[candidate()])['stale'])
        self.assertEqual(BuyerPreferenceState.objects.get().revision,revision)

    def test_job_completion_and_profile_projection_roll_back_together(self):
        turn=self.turn();service.enqueue_chat(turn);job=service.claim_job()
        original=service._save
        def fail_after_save(state,now):
            original(state,now)
            raise DatabaseError('synthetic transaction failure')
        with patch.object(service,'_save',side_effect=fail_after_save):
            with self.assertRaises(DatabaseError):
                service.complete_job(job.pk,job.lease_token,[candidate()],
                    extraction_rejections=[{'index':1,'reason':'quote_not_verbatim'}])
        self.assertEqual(PreferenceUpdateJob.objects.get().status,'running')
        self.assertEqual(PreferenceUpdateJob.objects.get().results,{})
        self.assertEqual(BuyerMemory.objects.count(),0)
        self.assertEqual(PreferenceAudit.objects.count(),0)

    def test_retry_is_bounded_and_error_content_is_not_persisted(self):
        turn=self.turn();job=service.enqueue_chat(turn)
        for attempt in range(5):
            job.refresh_from_db()
            when=max(timezone.now(),job.available_at)+timedelta(seconds=1)
            claim=service.claim_job(now=when)
            self.assertTrue(service.fail_job(claim.pk,claim.lease_token,'contains arbitrary private text',now=when))
        job.refresh_from_db()
        self.assertEqual(job.status,'dead')
        self.assertEqual(job.attempts,5)
        self.assertEqual(job.error_code,'PROFILE_PROCESSING_FAILED')

    def test_expired_last_attempt_is_terminal(self):
        turn=self.turn();job=service.enqueue_chat(turn)
        PreferenceUpdateJob.objects.filter(pk=job.pk).update(status='running',attempts=5,lease_until=timezone.now()-timedelta(seconds=1))
        self.assertIsNone(service.claim_job())
        self.assertEqual(PreferenceUpdateJob.objects.get().status,'dead')

    def test_disabled_queue_is_zero_query_and_cannot_complete_inflight_work(self):
        turn=self.turn();service.enqueue_chat(turn);job=service.claim_job()
        with override_settings(SUPPORT_AUTO_PROFILE_ENABLED=False),self.assertNumQueries(0):
            self.assertIsNone(service.enqueue_chat(turn))
            self.assertIsNone(service.claim_job())
            self.assertTrue(service.complete_job(job.pk,job.lease_token,[candidate()])['stale'])

    def test_disabled_account_during_extraction_does_not_create_profile(self):
        turn=self.turn();service.enqueue_chat(turn);job=service.claim_job()
        UserProfile.objects.filter(pk=self.user.pk).update(is_active=False)
        result=service.complete_job(job.pk,job.lease_token,[candidate()])
        self.assertEqual(result['reasons'],['account_unavailable'])
        self.assertEqual(PreferenceUpdateJob.objects.get().status,'done')
        self.assertFalse(BuyerPreferenceState.objects.exists())
        self.assertFalse(BuyerMemory.objects.exists())

    def test_role_change_during_extraction_does_not_create_profile(self):
        turn=self.turn();service.enqueue_chat(turn);job=service.claim_job()
        UserProfile.objects.filter(pk=self.user.pk).update(user_type='merchant')
        result=service.complete_job(job.pk,job.lease_token,[candidate()])
        self.assertEqual(result['reasons'],['account_unavailable'])
        self.assertFalse(BuyerPreferenceState.objects.exists())
        self.assertFalse(BuyerMemory.objects.exists())

    def test_deleted_account_event_is_completed_without_retries(self):
        turn=self.turn();service.enqueue_chat(turn);job=service.claim_job()
        self.user.delete()
        result=service.complete_job(job.pk,job.lease_token,[candidate()])
        self.assertEqual(result['reasons'],['account_unavailable'])
        job.refresh_from_db()
        self.assertEqual(job.status,'done')
        self.assertEqual(job.attempts,1)
        self.assertFalse(BuyerMemory.objects.exists())

    def test_inactive_behavior_owner_leaves_profile_state_unchanged(self):
        service.manual_preferences(self.user,{'categories':['绿茶']})
        service.enqueue_behavior(self.user.pk,'e'*64,timezone.now(),[behavior()])
        state=BuyerPreferenceState.objects.get()
        before=(state.revision,state.records,state.field_fences,state.updated_at)
        job=service.claim_job()
        UserProfile.objects.filter(pk=self.user.pk).update(is_active=False)
        result=service.complete_job(job.pk,job.lease_token,job.payload['candidates'])
        self.assertEqual(result['reasons'],['account_unavailable'])
        state.refresh_from_db()
        self.assertEqual((state.revision,state.records,state.field_fences,state.updated_at),before)
        self.assertEqual(BuyerMemory.objects.get().preferences['categories'],['绿茶'])

    def test_cross_database_transaction_configuration_is_rejected(self):
        with override_settings(AI_STORAGE_DB_ALIAS='ai_storage'):
            with self.assertRaises(ImproperlyConfigured):
                service.manual_preferences(self.user,{})


@override_settings(SUPPORT_AUTO_PROFILE_ENABLED=True, SUPPORT_PROFILE_CHAT_ENABLED=True,
                   SUPPORT_PROFILE_BEHAVIOR_ENABLED=True, AI_STORAGE_DB_ALIAS='default')
class AutoProfileConcurrencyTests(TransactionTestCase):
    def test_distinct_concurrent_updates_keep_both_terms(self):
        if connections['default'].vendor!='postgresql':
            self.skipTest('Real row lock behavior requires isolated PostgreSQL')
        user=UserProfile.objects.create(username='prof-race',user_type='customer',is_active=True)
        turns=[]
        for index,value in enumerate(['红茶','绿茶']):
            conversation=SupportConversation.objects.create(user=user)
            turns.append(SupportTurn.objects.create(user=user,conversation=conversation,request_id=uuid.uuid4(),
                request_hash='synthetic',sequence=1,user_text='我一直喜欢'+value,answer='合成',intent='question_answering',response={'tasks':[]}))
        barrier=Barrier(2)
        def apply(index):
            connections.close_all()
            try:
                turn=SupportTurn.objects.get(pk=turns[index].pk)
                barrier.wait(timeout=5)
                return service.apply_candidates(user.pk,[candidate(['红茶','绿茶'][index],quote=turn.user_text)],'chat',str(turn.pk),turn.created_at)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(apply,range(2)))
        self.assertTrue(all(x['applied']==1 for x in results))
        self.assertEqual(set(service.read_preferences(user)['preferences']['categories']),{'红茶','绿茶'})
        self.assertEqual(BuyerPreferenceState.objects.count(),1)

    def test_manual_field_replacement_wins_concurrent_old_extraction(self):
        if connections['default'].vendor!='postgresql':
            self.skipTest('Real row lock behavior requires isolated PostgreSQL')
        user=UserProfile.objects.create(username='fence-race',user_type='customer',is_active=True)
        conversation=SupportConversation.objects.create(user=user)
        turn=SupportTurn.objects.create(user=user,conversation=conversation,request_id=uuid.uuid4(),
            request_hash='synthetic',sequence=1,user_text='我一直喜欢红茶',answer='合成',intent='question_answering',response={'tasks':[]})
        service.manual_preferences(user,{'brands':['合成品牌']})
        barrier=Barrier(2)
        def apply(index):
            connections.close_all()
            try:
                barrier.wait(timeout=5)
                if index:
                    return service.manual_preferences(user,{'categories':['绿茶']})
                return service.apply_candidates(user.pk,[candidate('红茶',quote=turn.user_text)],'chat',str(turn.pk),turn.created_at)
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(apply,range(2)))
        final=service.read_preferences(user)['preferences']
        self.assertEqual(final['categories'],['绿茶'])
        self.assertEqual(final['brands'],['合成品牌'])
