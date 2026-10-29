"""Cross-process projection, counters, privacy and retrieval timing regressions."""
import copy
import json
import time
import uuid
from dataclasses import replace
from unittest.mock import patch

from django.test import TestCase
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult

from . import telemetry
from .configuration import AgentConfig
from .mcp_tracing import remote_observation, outgoing_context, import_report, remote_callback, MAX_SPANS
from .models import AgentSpan
from .query_rewrite import QueryPolicy


def config(**kwargs):
    return replace(AgentConfig('synthetic', 'disabled', True, False, '', 1), **kwargs)


class McpTracingTests(TestCase):
    def tearDown(self):
        telemetry.shutdown_telemetry()

    def report(self, parent):
        with remote_observation(parent, config()) as report:
            with telemetry.agent_span('knowledge.retrieve'):
                with telemetry.agent_span('knowledge.embedding') as span:
                    span.set_attribute('user.prompt','PRIVATE_PAYLOAD')
                callback = remote_callback()
                key = uuid.uuid4()
                callback.on_chat_model_start({},[['PRIVATE_PAYLOAD']],run_id=key)
                callback.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(content='PRIVATE_PAYLOAD',
                    usage_metadata={'input_tokens':12,'output_tokens':3,'total_tokens':15}))]]),run_id=key)
                telemetry.retrieval_hits(5)
        return report

    def test_same_trace_exact_parentage_and_totals_with_one_database_flush(self):
        with patch.object(AgentSpan.objects,'bulk_create',wraps=AgentSpan.objects.bulk_create) as insert:
            with telemetry.observe_agent(config()) as observation:
                with telemetry.agent_span('mcp.rpc'):
                    parent = outgoing_context()
                    report = self.report(parent)
                    self.assertEqual(import_report(report,parent),'complete')
                self.assertEqual(insert.call_count,0)
            self.assertEqual(insert.call_count,1)
        rows = list(AgentSpan.objects.all())
        self.assertEqual({r.trace_id for r in rows},{observation.trace_id})
        ids = {r.span_id for r in rows}
        self.assertTrue(all(not r.parent_span_id or r.parent_span_id in ids for r in rows))
        remote_ids = {r['span_id'] for r in report['spans']}
        self.assertTrue(remote_ids <= ids)
        root = AgentSpan.objects.get(name='support.chat')
        self.assertEqual(root.attributes['agent.retrieval.hits'],5)
        self.assertEqual(root.attributes['agent.llm.calls'],1)
        self.assertEqual(root.attributes['gen_ai.usage.input_tokens'],12)
        self.assertEqual(root.attributes['gen_ai.usage.output_tokens'],3)
        self.assertNotIn('PRIVATE_PAYLOAD',json.dumps(report))
        self.assertNotIn('PRIVATE_PAYLOAD',json.dumps([r.attributes for r in rows]))

    def test_wrong_trace_invalid_graph_and_private_fields_do_not_get_published(self):
        with telemetry.observe_agent(config()):
            with telemetry.agent_span('mcp.rpc'):
                parent = outgoing_context()
                report = self.report(parent)
                for mutate in (lambda r:r.update(trace_id='f'*32),
                               lambda r:r['spans'][0].update(parent_span_id='0'*16),
                               lambda r:r['spans'][0].update(end_ns=0),
                               lambda r:r['totals'].update(owner_id=1)):
                    broken=copy.deepcopy(report);mutate(broken)
                    self.assertEqual(import_report(broken,parent),'invalid')
        self.assertEqual(AgentSpan.objects.count(),2)

    def test_disabled_observation_sends_no_context_or_report(self):
        with telemetry.observe_agent(config(telemetry_enabled=False)):
            self.assertIsNone(outgoing_context())
            with remote_observation(None,config()) as report:
                self.assertIsNone(report)
                self.assertIsNone(remote_callback())
        self.assertFalse(AgentSpan.objects.exists())

    def test_missing_or_malformed_telemetry_does_not_change_valid_tool_result(self):
        from .mcp_client import AgentDataAccess
        from .mcp_testing import SyntheticMcpTransport
        from .mcp_security import read_private,write_private
        class Transport(SyntheticMcpTransport):
            def request(self,*args,**kwargs):
                reply=super().request(*args,**kwargs)
                grant=self.session.grant
                value=read_private(grant['private_dir'],'output',grant['nonce'],self.session.sequence)
                value['telemetry']={'unexpected':'PRIVATE_PAYLOAD'}
                write_private(grant['private_dir'],'output',value)
                return reply
        with patch('support_ai.mcp_client.StdioMcpTransport',Transport):
            with telemetry.observe_agent(config()):
                with AgentDataAccess(config=config(),message='synthetic',preview_history=[]) as access:
                    self.assertTrue(access.call('validate_categories',categories=[])['data']['valid'])
        rpc=AgentSpan.objects.get(name='mcp.rpc')
        self.assertEqual(rpc.attributes['agent.mcp.telemetry'],'invalid')
        self.assertNotIn('PRIVATE_PAYLOAD',json.dumps(list(AgentSpan.objects.values_list('attributes',flat=True))))

    def test_bridge_timeout_without_handoff_keeps_safe_error_and_missing_timing(self):
        from .mcp_client import AgentDataAccess, McpServiceError
        from .mcp_backend import failure
        with patch('support_ai.mcp_client.StdioMcpTransport') as transport:
            transport.return_value.tools={'validate_categories'}
            transport.return_value.request.return_value={'structuredContent':failure('BACKEND_TIMEOUT'),'isError':True}
            with telemetry.observe_agent(config()):
                with AgentDataAccess(config=config(),message='synthetic',preview_history=[]) as access:
                    with self.assertRaises(McpServiceError) as caught:
                        access.call('validate_categories',categories=[])
                    self.assertEqual(caught.exception.code,'BACKEND_TIMEOUT')
        rpc=AgentSpan.objects.get(name='mcp.rpc')
        self.assertEqual(rpc.status,'ERROR')
        self.assertEqual(rpc.attributes['agent.mcp.telemetry'],'unavailable')
        self.assertFalse(AgentSpan.objects.filter(name='mcp.backend.ready').exists())

    def test_long_report_is_bounded_and_keeps_parentage(self):
        with telemetry.observe_agent(config()):
            with telemetry.agent_span('mcp.rpc'):
                parent=outgoing_context()
                with remote_observation(parent,config()) as report:
                    with telemetry.agent_span('knowledge.retrieve'):
                        for _ in range(MAX_SPANS+5):
                            with telemetry.agent_span('knowledge.embedding'):
                                pass
                self.assertLessEqual(len(report['spans']),MAX_SPANS)
                self.assertGreater(report['dropped'],0)
                self.assertEqual(import_report(report,parent),'truncated')

    def test_cached_and_uncached_retrieval_count_evidence_once_and_time_real_work(self):
        from .retrieval import KnowledgeRetriever
        item={'chunk_id':1,'document_id':'public','text':'Green tea processing uses heat.',
              'source_title':'Synthetic public fixture'}
        for cached in (False,True):
            with self.subTest(cached=cached):
                with telemetry.observe_agent(config()):
                    with telemetry.agent_span('mcp.rpc'):
                        parent=outgoing_context()
                        with remote_observation(parent,config()) as report:
                            retriever=KnowledgeRetriever(None,config())
                            retriever.policy=QueryPolicy(max_queries=1,retry_enabled=False)
                            saved=([item],{'remaining_issues':[]}) if cached else None
                            with patch('support_ai.retrieval.evidence_key',return_value='synthetic'), \
                                 patch('support_ai.retrieval.cache_read',return_value=saved), \
                                 patch('support_ai.retrieval.hybrid_search_ready',return_value=True), \
                                 patch('support_ai.retrieval.search_knowledge_keywords',return_value=[item]), \
                                 patch('support_ai.retrieval.search_knowledge',return_value=[item]), \
                                 patch('support_ai.retrieval_cache.read',return_value=None), \
                                 patch('support_ai.retrieval.embed_text',return_value=[1.,0.]), \
                                 patch('support_ai.retrieval.cache_write'):
                                self.assertEqual(len(retriever.search('green tea')),1)
                        self.assertEqual(report['totals']['agent.retrieval.hits'],1)
                        self.assertEqual(import_report(report,parent),'complete')
                        names=[r['name'] for r in report['spans']]
                        self.assertEqual('knowledge.embedding' in names,not cached)
                        self.assertEqual('knowledge.keyword_search' in names,not cached)
                        self.assertEqual('knowledge.rerank.skipped' in names,not cached)
                        self.assertNotIn('knowledge.rerank',names)

    def test_analysis_subtracts_overlapping_children_once_and_reports_missing_segments(self):
        from .trace_analysis import analyze_spans
        def row(name,key,parent,start,duration):
            return dict(name=name,span_id=key,parent_span_id=parent,
                        started_at='2026-10-29T00:00:00.{}+00:00'.format(str(start).zfill(3)),
                        duration_ms=duration,status='OK',attributes={})
        result=analyze_spans([row('support.chat','a','',0,100),row('mcp.rpc','b','a',10,70),
                              row('knowledge.embedding','c','b',20,40),row('knowledge.keyword_search','d','b',30,40)])
        self.assertEqual(result['nodes'][0]['self_ms'],30)
        self.assertEqual(result['nodes'][1]['self_ms'],20)
        self.assertTrue(result['warnings'])
        self.assertEqual(result['duration_ms'],100)
