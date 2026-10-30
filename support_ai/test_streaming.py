"""Streaming boundaries, saved-turn replay and real provider SSE parsing (synthetic data)."""
import json
import threading
import uuid
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from django.http import JsonResponse
from django.test import LiveServerTestCase, SimpleTestCase, TransactionTestCase, override_settings
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from .streaming import (EventSink, StreamCancelled, bind_stream, checkpoint,
                        event_response, progress, verified_result)


def unpack(chunk):
    lines = chunk.decode('utf-8').splitlines()
    return lines[0][7:], json.loads(lines[1][6:])


class StreamProtocolTests(SimpleTestCase):
    def response(self, run):
        response = event_response(SimpleNamespace(), run)
        self.addCleanup(response.close)
        return response

    def test_first_frame_precedes_work_and_verified_answer_precedes_completion(self):
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def run():
            entered.set()
            progress('retrieval')
            verified_result({'step_id':'s1','tool':'greet_user','status':'success',
                             'data':{'answer':'您好，欢迎咨询。'}}, ['s1'])
            if not release.wait(5):
                raise AssertionError('Test barrier expired')
            return JsonResponse({'answer':'最终回答','conversation_id':'c1','revision':1})
        response = self.response(run)
        stream = iter(response.streaming_content)
        self.assertEqual(unpack(next(stream))[1]['stage'], 'accepted')
        self.assertFalse(entered.is_set())
        self.assertEqual(unpack(next(stream))[1]['stage'], 'retrieval')
        event, payload = unpack(next(stream))
        self.assertEqual(event, 'answer')
        self.assertEqual(payload, {'text':'您好，欢迎咨询。','provisional':True})
        release.set()
        tail = [unpack(c) for c in stream]
        self.assertEqual([e for e, _ in tail], ['answer', 'done'])
        self.assertEqual(tail[-1][1]['revision'], 1)

    def test_unverified_model_prose_never_leaves_sink(self):
        sink = EventSink()
        with bind_stream(sink):
            verified_result({'step_id':'s1','tool':'introduce_tea','status':'success',
                             'data':{'answer':'未经核验的草稿'}}, ['s1'])
            progress('arbitrary-private-content')
        self.assertTrue(sink.queue.empty())

    def test_verified_knowledge_is_released_with_its_source(self):
        sink = EventSink()
        data = {'answer':'绿茶采用杀青工艺。\n来源：资料A', 'grounding':{
            'status':'verified','claims':[{'text':'绿茶采用杀青工艺。','citations':[{'source_id':'e1'}]}],
            'sources':[{'source_id':'e1'}]}}
        with bind_stream(sink):
            verified_result({'step_id':'s1','tool':'introduce_tea','status':'success','data':data}, ['s1'])
        self.assertEqual(sink.queue.get_nowait()[1]['text'], data['answer'])

    def test_error_is_terminal_without_done_or_private_exception(self):
        def run():
            raise RuntimeError('password=synthetic-private-secret')
        frames = [unpack(c) for c in self.response(run).streaming_content]
        self.assertEqual(frames[-1][0], 'error')
        self.assertEqual(frames[-1][1]['status'], 503)
        self.assertNotIn('synthetic-private-secret', json.dumps(frames))
        self.assertNotIn('done', [e for e, _ in frames])

    def test_conflict_keeps_its_status_in_stream(self):
        frames = [unpack(c) for c in self.response(
            lambda: JsonResponse({'error':'会话已更新'}, status=409)).streaming_content]
        self.assertEqual(frames[-1], ('error', {'error':'会话已更新','status':409}))

    def test_close_before_first_iteration_releases_capacity_without_running(self):
        slots = threading.BoundedSemaphore(1)
        called = threading.Event()
        with patch('support_ai.streaming._slots', slots):
            response = self.response(lambda: called.set())
            self.assertIsNone(event_response(SimpleNamespace(), lambda: None))
            response.close()
            response.close()
            self.assertTrue(slots.acquire(blocking=False))
            slots.release()
        self.assertFalse(called.is_set())

    def test_disconnect_stops_future_steps_and_releases_worker(self):
        release, stopped = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        slots = threading.BoundedSemaphore(1)
        def run():
            progress('orders')
            release.wait(5)
            try:
                checkpoint()
            except StreamCancelled:
                stopped.set()
                raise
            raise AssertionError('Disconnected work continued')
        with patch('support_ai.streaming._slots', slots):
            response = self.response(run)
            stream = iter(response.streaming_content)
            next(stream)
            next(stream)
            response.close()
            release.set()
            self.assertTrue(stopped.wait(5))
            # Worker cleanup can follow the checkpoint by a scheduling interval.
            self.assertTrue(slots.acquire(timeout=5))
            slots.release()

    def test_slow_consumer_has_bounded_queue_and_still_receives_terminal(self):
        def run():
            from .streaming import _sink
            for i in range(100):
                _sink.get().put('answer', {'text':str(i),'provisional':True})
            self.assertLessEqual(_sink.get().queue.qsize(), 32)
            return JsonResponse({'answer':'最终回答','revision':1})
        frames = [unpack(c) for c in self.response(run).streaming_content]
        self.assertEqual(frames[-1][0], 'done')
        self.assertEqual(frames[-2][1]['text'], '最终回答')


class StreamingChatTests(TransactionTestCase):
    databases = {'default', 'ai_storage'}

    def setUp(self):
        from users.models import UserProfile
        from tea_saas.utils import jwt_encode
        self.user = UserProfile.objects.create(username='stream-test', password='synthetic',
                                               email='stream@example.test', is_active=True)
        self.auth = {'HTTP_AUTHORIZATION':'Bearer '+jwt_encode({'id':self.user.pk})}

    def post(self, body, streaming=True, auth=True):
        return self.client.post('/v1/support/chat/', data=json.dumps(body), content_type='application/json',
            HTTP_ACCEPT='text/event-stream' if streaming else 'application/json', **(self.auth if auth else {}))

    def consume(self, response):
        try:
            return [unpack(c) for c in response.streaming_content]
        finally:
            response.close()

    def test_validation_and_authentication_stay_http_errors(self):
        self.assertEqual(self.post({'message':'你好'}, auth=False).status_code, 401)
        bad = self.post({'message':''})
        self.assertEqual(bad.status_code, 400)
        self.assertFalse(bad.streaming)

    def test_fixed_reply_committed_once_and_replays_across_accept_types(self):
        from .models import SupportTurn
        body = {'message':'你好','request_id':str(uuid.uuid4())}
        with patch('support_ai.model_client.configured_model', side_effect=AssertionError('No model needed')):
            response = self.post(body)
            self.assertEqual(response['Content-Type'], 'text/event-stream; charset=utf-8')
            self.assertEqual(response['X-Accel-Buffering'], 'no')
            frames = self.consume(response)
            final = frames[-1][1]
            self.assertEqual(frames[-1][0], 'done')
            self.assertEqual(SupportTurn.objects.count(), 1)
            self.assertEqual(self.post(body, streaming=False).json(), final)
            self.assertEqual(self.consume(self.post(body))[-1], ('done', final))
        self.assertEqual(SupportTurn.objects.count(), 1)
        self.assertEqual(final['revision'], 1)

    def test_stale_revision_yields_error_and_no_new_turn(self):
        from .models import SupportTurn
        final = self.consume(self.post({'message':'你好'}))[-1][1]
        frames = self.consume(self.post({'message':'你好','conversation_id':final['conversation_id'],
                                        'expected_revision':0}))
        self.assertEqual(frames[-1][0], 'error')
        self.assertEqual(frames[-1][1]['status'], 409)
        self.assertEqual(SupportTurn.objects.count(), 1)

    def test_knowledge_runs_normal_mcp_graph_and_streams_only_verified_text(self):
        from .mcp_testing import enable_synthetic_mcp
        from .tests import FakeModel
        from .test_grounding import SOURCE
        enable_synthetic_mcp(self)
        model = FakeModel({'recommendation':.1,'question_answering':.9,'after_sales':.1})
        with patch('support_ai.model_client.configured_model', return_value=model), patch(
                'support_ai.retrieval.retrieve_knowledge', return_value=[SOURCE]):
            frames = self.consume(self.post({'message':'介绍一下绿茶'}))
        self.assertEqual(frames[-1][0], 'done')
        final = frames[-1][1]
        self.assertEqual(final['grounding']['knowledge'][0]['status'], 'verified')
        partial = [data for event, data in frames if event == 'answer' and data['provisional']]
        self.assertEqual(len(partial), 1)
        self.assertEqual(partial[0]['text'], final['answer'])
        self.assertTrue(final['knowledge_sources'])

    def test_failed_knowledge_reviewer_never_streams_draft_or_saves_turn(self):
        from .mcp_testing import enable_synthetic_mcp
        from .tests import FakeModel
        from .test_grounding import SOURCE
        from .grounding import GroundingReview
        from .models import SupportTurn
        from langchain_core.runnables import RunnableLambda
        enable_synthetic_mcp(self)
        model = FakeModel({'recommendation':.1,'question_answering':.9,'after_sales':.1})
        structured = model.with_structured_output
        def fail(prompt):
            raise TimeoutError('synthetic-review-failure')
        with patch.object(model, 'with_structured_output', side_effect=lambda schema:
                RunnableLambda(fail) if schema is GroundingReview else structured(schema)), patch(
                'support_ai.model_client.configured_model', return_value=model), patch(
                'support_ai.retrieval.retrieve_knowledge', return_value=[SOURCE]):
            frames = self.consume(self.post({'message':'介绍一下绿茶'}))
        self.assertEqual(frames[-1][0], 'error')
        self.assertEqual(frames[-1][1]['status'], 503)
        self.assertNotIn(SOURCE['text'], json.dumps(frames, ensure_ascii=False))
        self.assertEqual(SupportTurn.objects.count(), 0)


class ProviderStreamTests(SimpleTestCase):
    def test_real_langchain_sse_aggregation_preserves_schema_and_token_accounting(self):
        from .model_client import configured_model
        from .cost_control import model_request
        class Slot(BaseModel):
            value: str
        requests = []
        def reply(request):
            body = json.loads(request.content)
            requests.append(body)
            tool = body['tools'][0]['function']['name']
            chunks = [
                {'choices':[{'index':0,'delta':{'role':'assistant','tool_calls':[{
                    'index':0,'id':'call_test','type':'function','function':{
                        'name':tool,'arguments':'{"value":'}}]},'finish_reason':None}]},
                {'choices':[{'index':0,'delta':{'tool_calls':[{'index':0,'function':{
                    'arguments':'"绿茶"}'}}]},'finish_reason':None}]},
                {'choices':[{'index':0,'delta':{},'finish_reason':'tool_calls'}]},
                {'choices':[],'usage':{'prompt_tokens':40,'completion_tokens':10,'total_tokens':50}},
            ]
            text = ''.join('data: '+json.dumps(dict(c, id='stream-test', object='chat.completion.chunk',
                model='synthetic-model'))+'\n\n' for c in chunks)+'data: [DONE]\n\n'
            return httpx.Response(200, headers={'Content-Type':'text/event-stream'}, content=text.encode())
        with httpx.Client(transport=httpx.MockTransport(reply)) as http, override_settings(
                SUPPORT_API_KEY='synthetic-no-network', SUPPORT_BASE_URL='https://example.invalid/v1'):
            model = configured_model()
            model.client.http_client = http
            # The OpenAI SDK already holds its HTTP client; bind the mock there.
            from openai import OpenAI
            model.client.client = OpenAI(api_key='synthetic', base_url='https://example.invalid/v1',
                                          http_client=http).chat.completions
            with model_request() as budget:
                value = model.with_structured_output(Slot).invoke([HumanMessage(content='推荐茶')])
        self.assertEqual(value.value, '绿茶')
        self.assertTrue(requests[0]['stream'])
        self.assertEqual(requests[0]['stream_options'], {'include_usage':True})
        self.assertEqual(budget.snapshot()['input_tokens'], 40)
        self.assertEqual(budget.snapshot()['output_tokens'], 10)


class StreamingWireTests(LiveServerTestCase):
    databases = {'default', 'ai_storage'}

    def test_real_http_delivers_frames_before_commit_and_replay_does_not_duplicate(self):
        import requests
        from .context import commit_turn
        from .models import SupportTurn
        from users.models import UserProfile
        from tea_saas.utils import jwt_encode
        user = UserProfile.objects.create(username='stream-wire', password='synthetic',
                                          email='wire@example.test', is_active=True)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)
        def gated_commit(*args, **kwargs):
            entered.set()
            if not release.wait(10):
                raise AssertionError('Wire-test barrier expired')
            return commit_turn(*args, **kwargs)
        body = {'message':'你好','request_id':str(uuid.uuid4())}
        headers = {'Authorization':'Bearer '+jwt_encode({'id':user.pk}), 'Accept':'text/event-stream'}
        with requests.Session() as session, patch('support_ai.views.commit_turn', gated_commit):
            session.trust_env = False
            with session.post(self.live_server_url+'/v1/support/chat/', json=body,
                              headers=headers, stream=True, timeout=15) as response:
                self.assertEqual(response.status_code, 200)
                lines = response.iter_lines(chunk_size=1, decode_unicode=True)
                self.assertEqual(next(lines), 'event: status')
                self.assertEqual(json.loads(next(lines)[6:])['stage'], 'accepted')
                self.assertTrue(entered.wait(5))
                self.assertEqual(SupportTurn.objects.filter(user=user).count(), 0)
                release.set()
                frames = '\n'.join(lines)
                self.assertIn('event: done', frames)
                self.assertIn('"revision": 1', frames)
            replay = session.post(self.live_server_url+'/v1/support/chat/', json=body,
                headers=dict(headers, Accept='application/json'), timeout=10)
            self.assertEqual(replay.status_code, 200)
            self.assertEqual(replay.json()['revision'], 1)
        self.assertEqual(SupportTurn.objects.filter(user=user).count(), 1)
