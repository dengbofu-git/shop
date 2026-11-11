"""Committed-chat/API/worker/soft-ranking integration on synthetic PostgreSQL data."""
from datetime import timedelta
import json
from types import SimpleNamespace
import uuid
from unittest.mock import Mock, patch

from django.db import DatabaseError, transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from ai_storage.models import BuyerMemory
from ai_storage.profile_models import BuyerPreferenceState, PreferenceUpdateJob
from ai_storage.profile_service import manual_preferences, read_preferences
from goods.models import Catalog, SKU, SPU
from tea_saas.utils import jwt_encode
from users.models import UserProfile

from .bundle_recommendations import recommend_bundle
from .context import commit_turn
from .contracts import RecommendationIntent
from .mcp_client import AgentDataAccess
from .mcp_testing import SyntheticMcpTransport, config
from .models import SupportConversation, SupportTurn
from .profile_worker import process_next
from .recommendations import match_products
from .test_profile_extraction import FakeExtractionModel, candidate


@override_settings(SUPPORT_AUTO_PROFILE_ENABLED=True, SUPPORT_TASK_STATE_ENABLED=False,
                   SUPPORT_PROFILE_CHAT_ENABLED=True, SUPPORT_PROFILE_BEHAVIOR_ENABLED=True,
                   AI_STORAGE_DB_ALIAS='default', SUPPORT_MCP_TRANSPORT='stdio')
class AutoProfileFlowTests(TestCase):
    databases = {'default'}

    def setUp(self):
        self.user=UserProfile.objects.create(username='prof-flow1',is_active=True,user_type='customer')
        self.other=UserProfile.objects.create(username='prof-flow2',is_active=True,user_type='customer')
        self.merchant=UserProfile.objects.create(username='prof-shop',is_active=True,user_type='merchant')
        self.client.defaults.update(HTTP_AUTHORIZATION='Bearer '+jwt_encode({'id':self.user.pk}),
                                    HTTP_X_SUPPORT_CONTRACT='focused-query-v1')

    @staticmethod
    def response(**extra):
        return {'intent':'question_answering','answer':'合成测试回复','tasks':[],**extra}

    def commit(self,text='我平时喜欢乌龙茶',*,request_id=None,response=None):
        request_id=request_id or uuid.uuid4()
        result=commit_turn(self.user,None,0,request_id,'synthetic-flow',text,
                           self.response() if response is None else response)
        return SupportTurn.objects.get(user=self.user,request_id=request_id),result

    def extract(self,text='我平时喜欢乌龙茶',value='乌龙茶',polarity='like'):
        return FakeExtractionModel({'candidates':[candidate(text,value,polarity)]})

    def put(self,values):
        return self.client.put('/v1/support/preferences/',json.dumps(values),content_type='application/json')

    def preferences(self):
        response=self.client.get('/v1/support/preferences/')
        self.assertEqual(response.status_code,200,response.content)
        return response.json()['preferences']

    def product(self,name,category,price='20.00'):
        category,_=Catalog.objects.get_or_create(name=category)
        product=SPU.objects.create(name=name,catalog=category,merchant=self.merchant)
        return SKU.objects.create(name='合成规格',spu=product,price=price,market_price=price,
                                   cost_price='1.00',stock=10,is_launched=True)

    def test_commit_only_queues_and_worker_applies_afterward(self):
        turn,_=self.commit()
        self.assertFalse(BuyerMemory.objects.filter(owner_id=self.user.pk).exists())
        job=PreferenceUpdateJob.objects.get()
        self.assertEqual((job.owner_id,job.source_ref),(self.user.pk,str(turn.pk)))
        self.assertIsNotNone(job.source_at)
        self.assertLessEqual(job.source_at,turn.created_at)
        self.assertEqual(job.payload,{})
        model=self.extract()
        self.assertEqual(process_next(model=model)['status'],'done')
        self.assertEqual(len(model.calls),1)
        self.assertEqual(self.preferences()['categories'],['乌龙茶'])
        self.assertNotIn('source_ref',json.dumps(self.preferences()))

    def test_rollback_removes_both_chat_and_outbox(self):
        with self.assertRaisesRegex(RuntimeError,'abort'):
            with transaction.atomic():
                self.commit()
                self.assertEqual(PreferenceUpdateJob.objects.count(),1)
                raise RuntimeError('abort')
        self.assertEqual(SupportTurn.objects.count(),0)
        self.assertEqual(SupportConversation.objects.count(),0)
        self.assertEqual(PreferenceUpdateJob.objects.count(),0)

    def test_outbox_storage_failure_rolls_back_the_source_turn(self):
        with patch('ai_storage.profile_service.enqueue_chat',side_effect=DatabaseError('synthetic outbox failure')):
            with self.assertRaises(DatabaseError):
                self.commit()
        self.assertFalse(SupportTurn.objects.exists())
        self.assertFalse(SupportConversation.objects.exists())
        self.assertFalse(PreferenceUpdateJob.objects.exists())

    def test_failed_blocked_and_partial_turns_never_enqueue(self):
        for response in [self.response(error='synthetic'),self.response(compliance_blocked=True),
                         self.response(completion_status='partial'),self.response(tasks=[{'status':'error'}])]:
            self.commit(response=response)
        self.assertEqual(SupportTurn.objects.count(),4)
        self.assertFalse(PreferenceUpdateJob.objects.exists())

    def test_replay_is_one_source_and_one_job(self):
        request_id=uuid.uuid4()
        first,one=self.commit(request_id=request_id)
        second,two=self.commit(request_id=request_id)
        self.assertEqual(first.pk,second.pk)
        self.assertEqual(one,two)
        self.assertEqual(PreferenceUpdateJob.objects.count(),1)
        model=self.extract()
        self.assertEqual(process_next(model=model)['status'],'done')
        self.assertEqual(process_next(model=model)['status'],'idle')
        self.assertEqual(len(model.calls),1)

    def test_deleted_or_foreign_source_never_reaches_extractor(self):
        turn,_=self.commit()
        turn.delete()
        model=self.extract()
        self.assertEqual(process_next(model=model)['status'],'done')
        self.assertFalse(model.calls)
        self.assertFalse(BuyerMemory.objects.exists())
        turn,_=self.commit()
        PreferenceUpdateJob.objects.filter(source_ref=str(turn.pk)).update(owner_id=self.other.pk)
        self.assertEqual(process_next(model=model)['status'],'done')
        self.assertFalse(model.calls)
        self.assertFalse(BuyerMemory.objects.exists())

    def test_explicit_negative_correction_replaces_old_like(self):
        self.commit('我平时喜欢红茶')
        self.assertEqual(process_next(model=self.extract('我平时喜欢红茶','红茶'))['status'],'done')
        self.commit('我不再喜欢红茶')
        self.assertEqual(process_next(model=self.extract('我不再喜欢红茶','红茶','hate'))['status'],'done')
        values=self.preferences()
        self.assertEqual(values['categories'],[])
        self.assertEqual(values['disliked_categories'],['红茶'])

    def test_manual_delete_blocks_old_unknown_candidate(self):
        turn,_=self.commit()
        future=turn.created_at+timedelta(minutes=1)
        with patch('ai_storage.profile_service.timezone.now',return_value=future):
            response=self.client.delete('/v1/support/preferences/')
        self.assertEqual(response.status_code,200,response.content)
        result=process_next(model=self.extract(),now=future+timedelta(minutes=1))
        self.assertEqual(result['status'],'done')
        self.assertEqual(self.preferences()['categories'],[])
        self.assertIn('before_manual_reset',PreferenceUpdateJob.objects.get().results['reasons'])

    def test_manual_field_edit_blocks_old_candidate_not_yet_in_profile(self):
        turn,_=self.commit('我平时喜欢红茶')
        future=turn.created_at+timedelta(minutes=1)
        with patch('ai_storage.profile_service.timezone.now',return_value=future):
            response=self.put({'categories':['绿茶']})
        self.assertEqual(response.status_code,200,response.content)
        process_next(model=self.extract('我平时喜欢红茶','红茶'),now=future+timedelta(minutes=1))
        self.assertEqual(self.preferences()['categories'],['绿茶'])

    def test_legacy_three_field_put_preserves_unsubmitted_dislikes(self):
        self.assertEqual(self.put({'disliked_categories':['红茶']}).status_code,200)
        response=self.put({'categories':['绿茶'],'brands':[],'keywords':[]})
        self.assertEqual(response.status_code,200,response.content)
        self.assertEqual(self.preferences()['disliked_categories'],['红茶'])

    def test_invalid_manual_polarity_conflict_is_400_without_overwriting(self):
        self.assertEqual(self.put({'categories':['绿茶']}).status_code,200)
        response=self.put({'categories':['红茶'],'disliked_categories':['红茶']})
        self.assertEqual(response.status_code,400,response.content)
        self.assertEqual(self.preferences()['categories'],['绿茶'])

    def test_normalized_brand_polarity_conflict_is_400_not_server_error(self):
        self.assertEqual(self.put({'brands':['青山']}).status_code,200)
        response=self.put({'brands':['ＴＥＡ  ＨＯＵＳＥ'],'disliked_brands':['TEA HOUSE']})
        self.assertEqual(response.status_code,400,response.content)
        self.assertEqual(self.preferences()['brands'],['青山'])

    def test_profile_capacity_is_409_without_echoing_submitted_preference(self):
        value='不应回显的品牌词'
        with patch('ai_storage.profile_service.manual_preferences',side_effect=ValueError('profile_capacity')):
            response=self.put({'keywords':[value]})
        self.assertEqual(response.status_code,409,response.content)
        self.assertEqual(response.json()['error_code'],'PROFILE_CAPACITY')
        self.assertNotIn(value,response.content.decode('utf-8'))
        self.assertFalse(PreferenceUpdateJob.objects.exists())

    def test_disabled_worker_never_claims_or_calls_model(self):
        self.commit()
        model=self.extract()
        with override_settings(SUPPORT_AUTO_PROFILE_ENABLED=False),self.assertNumQueries(0):
            self.assertEqual(process_next(model=model),{'status':'disabled'})
        self.assertFalse(model.calls)
        self.assertEqual(PreferenceUpdateJob.objects.get().status,'queued')

    def test_provider_failure_retries_job_without_private_error_text(self):
        self.commit()
        model=FakeExtractionModel(error=TimeoutError('private test@example.com raw user statement'))
        result=process_next(model=model)
        self.assertEqual(result,{'status':'retry_or_dead','error_code':'MODEL_OR_SCHEMA_FAILURE'})
        job=PreferenceUpdateJob.objects.get()
        self.assertEqual((job.status,job.attempts,job.error_code),('queued',1,'MODEL_OR_SCHEMA_FAILURE'))
        self.assertGreater(job.available_at,job.created_at)
        self.assertNotIn('test@example.com',json.dumps(job.results))
        self.assertNotIn('raw user statement',job.error_code)
        self.assertFalse(BuyerMemory.objects.exists())

    def test_rejected_extraction_audit_contains_no_candidate_text(self):
        self.commit()
        model=self.extract('我平时喜欢红茶','红茶')
        self.assertEqual(process_next(model=model)['status'],'done')
        job=PreferenceUpdateJob.objects.get()
        self.assertEqual(job.results['extraction_rejections'],[{'index':0,'reason':'quote_not_verbatim'}])
        self.assertNotIn('红茶',json.dumps(job.results,ensure_ascii=False))
        self.assertEqual(self.preferences()['categories'],[])

    def test_operator_retry_is_disabled_without_database_queries(self):
        from .profile_worker import retry_dead_job
        with override_settings(SUPPORT_AUTO_PROFILE_ENABLED=False),self.assertNumQueries(0):
            self.assertFalse(retry_dead_job(uuid.uuid4()))

    def test_operator_retry_only_requeues_dead_preserving_event_identity(self):
        from .profile_worker import retry_dead_job
        source_at=timezone.now()-timedelta(days=1)
        job=PreferenceUpdateJob.objects.create(event_key='behavior-operator-fixture',owner_id=self.user.pk,
            source_type='behavior',source_ref='behavior-owned-event',source_at=source_at,status='dead',attempts=5,
            error_code='BEHAVIOR_SOURCE_FAILURE',payload={'generation':8,'fingerprint':'b'*64,
                'candidates':[],'evidence':{'source_type':'purchase_statistics'}})
        identity=(job.pk,job.event_key,job.owner_id,job.source_type,job.source_ref,job.source_at,job.created_at)
        original_payload=dict(job.payload)
        now=timezone.now()
        self.assertTrue(retry_dead_job(job.pk,now=now))
        job.refresh_from_db()
        self.assertEqual((job.pk,job.event_key,job.owner_id,job.source_type,job.source_ref,job.source_at,job.created_at),identity)
        self.assertEqual((job.status,job.attempts,job.error_code),('queued',0,''))
        self.assertEqual(job.payload['operator_retry_count'],1)
        self.assertEqual(job.payload['operator_prior_attempts'],5)
        for field,value in original_payload.items():
            self.assertEqual(job.payload[field],value)
        self.assertEqual(job.available_at,now)
        for status in ('queued','running','done'):
            job.status=status
            job.save(update_fields=['status'])
            self.assertFalse(retry_dead_job(job.pk,now=now))
            job.refresh_from_db()
            self.assertEqual(job.status,status)
            self.assertEqual(job.payload['operator_retry_count'],1)
        job.status='dead'
        job.attempts=2
        job.save(update_fields=['status','attempts'])
        self.assertTrue(retry_dead_job(job.pk,now=now))
        job.refresh_from_db()
        self.assertEqual(job.payload['operator_retry_count'],2)
        self.assertEqual(job.payload['operator_prior_attempts'],7)
        self.assertEqual(job.payload['fingerprint'],original_payload['fingerprint'])

    def test_negative_ranking_never_filters_explicit_current_requirement(self):
        red=self.product('山香红茶','红茶')
        green=self.product('春香绿茶','绿茶')
        unrestricted=match_products(RecommendationIntent(action='SEARCH'),soft_dislikes={'categories':['红茶']})
        self.assertEqual([r['sku_id'] for r in unrestricted['recommendations']],[green.pk,red.pk])
        hard=RecommendationIntent(action='SEARCH',required={'categories':['红茶']})
        chosen=match_products(hard,soft_dislikes={'categories':['红茶']})
        self.assertEqual(chosen['recommendation_status'],'MATCHED')
        self.assertEqual([r['sku_id'] for r in chosen['recommendations']],[red.pk])
        self.assertEqual(hard.excluded.categories,[])

    def test_bundle_with_only_disliked_inventory_remains_feasible(self):
        red=self.product('山香红茶','红茶')
        intent=RecommendationIntent(action='SEARCH',required={'price_basis':'total','budget_max':'100.00',
            'currency':'CNY','composition':'single','budget_mode':'cap'})
        result=recommend_bundle(intent,soft_dislikes={'categories':['红茶']})
        self.assertEqual(result['recommendation_status'],'MATCHED')
        self.assertTrue(result['recommendation_bundles'])
        self.assertEqual({item['sku_id'] for b in result['recommendation_bundles'] for item in b['items']},{red.pk})
        self.assertTrue(all(b['within_budget'] for b in result['recommendation_bundles']))

    def test_mcp_projects_only_owned_preferences_not_private_provenance(self):
        manual_preferences(self.user,{'disliked_categories':['红茶']})
        manual_preferences(self.other,{'categories':['白茶']})
        state=BuyerPreferenceState.objects.get(owner_id=self.user.pk)
        records=state.records
        records['category:红茶']['source_ref']='private-profile-event-secret'
        records['category:红茶']['evidence']={'private_order_id':'private-order-secret'}
        state.records=records
        state.save(update_fields=['records'])
        red=self.product('山香红茶','红茶')
        green=self.product('春香绿茶','绿茶')
        with patch('support_ai.mcp_client.StdioMcpTransport',SyntheticMcpTransport):
            access=AgentDataAccess(config=config(),message='推荐商品',owner_id=self.user.pk)
            self.addCleanup(access.close)
            memory=access.preferences()
            self.assertEqual(memory['preferences']['disliked_categories'],['红茶'])
            self.assertNotIn('白茶',json.dumps(memory,ensure_ascii=False))
            encoded=json.dumps(memory,ensure_ascii=False)
            for private in ('private-profile-event-secret','private-order-secret','evidence','source_ref','quote'):
                self.assertNotIn(private,encoded)
            products=access.call('search_products',intent=RecommendationIntent(action='SEARCH').model_dump(),limit=2)
            self.assertEqual([r['sku_id'] for r in products['data']['recommendations']],[green.pk,red.pk])

    def test_http_chat_commits_outbox_once_without_extracting_in_request(self):
        response=self.response()
        graph=SimpleNamespace(invoke=lambda *args,**kwargs:{'response':response,'tool_results':[]})
        data=SimpleNamespace(search=Mock(),close=Mock(),preference_unavailable=False)
        body={'message':'我平时喜欢乌龙茶','request_id':str(uuid.uuid4())}
        with patch('support_ai.configuration.effective_configuration',return_value=config()),\
             patch('support_ai.model_client.lazy_configured_model',return_value=None),\
             patch('support_ai.views.AgentDataAccess',return_value=data),\
             patch('support_ai.views.load_agent_preferences',return_value=None),\
             patch('support_ai.workflow.build_graph',return_value=graph),\
             patch('support_ai.profile_extraction.extract_candidates') as extractor:
            first=self.client.post('/v1/support/chat/',json.dumps(body),content_type='application/json')
            replayed=self.client.post('/v1/support/chat/',json.dumps(body),content_type='application/json')
        self.assertEqual(first.status_code,200,first.content)
        self.assertEqual(replayed.json(),first.json())
        self.assertEqual(SupportTurn.objects.count(),1)
        self.assertEqual(PreferenceUpdateJob.objects.count(),1)
        extractor.assert_not_called()

    def test_failed_http_generation_creates_no_source_or_profile_job(self):
        graph=SimpleNamespace(invoke=Mock(side_effect=RuntimeError('synthetic generation failure')))
        data=SimpleNamespace(search=Mock(),close=Mock(),preference_unavailable=False)
        with patch('support_ai.configuration.effective_configuration',return_value=config()),\
             patch('support_ai.model_client.lazy_configured_model',return_value=None),\
             patch('support_ai.views.AgentDataAccess',return_value=data),\
             patch('support_ai.views.load_agent_preferences',return_value=None),\
             patch('support_ai.workflow.build_graph',return_value=graph):
            response=self.client.post('/v1/support/chat/',json.dumps({
                'message':'我平时喜欢乌龙茶','request_id':str(uuid.uuid4())}),content_type='application/json')
        self.assertEqual(response.status_code,503,response.content)
        self.assertFalse(SupportTurn.objects.exists())
        self.assertFalse(PreferenceUpdateJob.objects.exists())

    def test_http_client_cannot_supply_profile_source_time(self):
        for field in ('profile_source_at','source_at','received_at'):
            response=self.client.post('/v1/support/chat/',json.dumps({
                'message':'我平时喜欢乌龙茶','request_id':str(uuid.uuid4()),
                field:'2999-01-01T00:00:00Z'}),content_type='application/json')
            self.assertEqual(response.status_code,400,response.content)
        self.assertFalse(SupportTurn.objects.exists())
        self.assertFalse(PreferenceUpdateJob.objects.exists())

    def test_normalized_brand_keeps_verbatim_quote_across_extraction_and_storage(self):
        text = 'I always like ＴＥＡ  ＨＯＵＳＥ.'
        self.commit(text)
        model = FakeExtractionModel({'candidates': [candidate(text, 'TEA HOUSE', kind='brand')]})
        result = process_next(model=model)
        self.assertEqual(result['status'], 'done')
        self.assertEqual(read_preferences(self.user)['preferences']['brands'], ['TEA HOUSE'])
        record = next(iter(BuyerPreferenceState.objects.get(owner_id=self.user.pk).records.values()))
        self.assertEqual(record['quote'], text)

    def test_known_category_alias_correction_updates_one_term_without_rewriting_quote(self):
        self.commit('我平时喜欢乌龙茶')
        process_next(model=self.extract())
        text = 'I no longer like oolong tea'
        self.commit(text)
        process_next(model=FakeExtractionModel({'candidates': [candidate(text, 'oolong tea', 'hate')]}))
        memory = read_preferences(self.user)['preferences']
        self.assertEqual(memory['categories'], [])
        self.assertEqual(memory['disliked_categories'], ['oolong tea'])
        records = BuyerPreferenceState.objects.get(owner_id=self.user.pk).records
        self.assertEqual(len(records), 1)
        self.assertEqual(next(iter(records.values()))['quote'], text)

    def test_manual_known_category_alias_polarity_conflict_is_rejected(self):
        response = self.put({'categories': ['乌龙茶'], 'disliked_categories': ['oolong tea']})
        self.assertEqual(response.status_code, 400)
