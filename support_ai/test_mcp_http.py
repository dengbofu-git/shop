"""Resident client failure isolation and secret/header boundary; no live services."""
import json
from unittest.mock import MagicMock, patch

import requests
from django.test import SimpleTestCase, override_settings

from .mcp_client import AgentDataAccess, McpServiceError
from .mcp_http import HttpMcpTransport
from .mcp_testing import config

TOKEN='synthetic-service-key-not-a-real-secret-000000'


@override_settings(SUPPORT_MCP_TRANSPORT='http',SUPPORT_MCP_URL='http://127.0.0.1:18082/mcp',
                   SUPPORT_MCP_SERVICE_TOKEN=TOKEN)
class HttpMcpClientTests(SimpleTestCase):
    def test_unified_launcher_waits_for_owned_service_before_starting_web(self):
        from .management.commands.run_support_backend import Command
        events=[]
        process,web=MagicMock(),MagicMock()
        web.poll.return_value=0
        web.returncode=0
        def ready(*args):
            events.append('ready')
        def spawn(*args,**kwargs):
            events.append('web')
            return web
        path='support_ai.management.commands.run_support_backend.'
        with patch(path+'start_service',return_value=(process,'instance')), \
             patch(path+'wait_ready',side_effect=ready),patch(path+'subprocess.Popen',side_effect=spawn), \
             patch(path+'stop_service') as stop:
            Command().handle(addrport='127.0.0.1:8000',mcp_port=18082,mcp_workers=2)
        self.assertEqual(events,['ready','web'])
        stop.assert_called_once_with(process)

    def test_failed_prewarm_never_starts_web_and_only_stops_owned_service(self):
        from .management.commands.run_support_backend import Command
        from django.core.management.base import CommandError
        process=MagicMock()
        path='support_ai.management.commands.run_support_backend.'
        with patch(path+'start_service',return_value=(process,'instance')), \
             patch(path+'wait_ready',side_effect=RuntimeError('Owned service not ready')), \
             patch(path+'subprocess.Popen') as web,patch(path+'stop_service') as stop:
            with self.assertRaises(CommandError):
                Command().handle(addrport='127.0.0.1:8000',mcp_port=18082,mcp_workers=2)
        web.assert_not_called()
        stop.assert_called_once_with(process)

    def test_offline_service_never_spawns_a_process_or_reads_data_locally(self):
        with patch('support_ai.mcp_http.requests.Session') as session, \
             patch('support_ai.mcp_client.subprocess.Popen') as spawn:
            session.return_value.post.side_effect=requests.ConnectionError('PRIVATE_ERROR_PAYLOAD')
            with AgentDataAccess(config=config(),message='synthetic',preview_history=[]) as access:
                with self.assertRaises(McpServiceError) as caught:
                    access.call('validate_categories',categories=[])
                self.assertEqual(caught.exception.code,'SERVICE_UNAVAILABLE')
                self.assertNotIn('PRIVATE_ERROR_PAYLOAD',str(caught.exception))
            spawn.assert_not_called()

    def test_service_key_and_grant_only_enter_headers_never_tool_arguments(self):
        def response(value,status=200):
            result=MagicMock()
            result.__enter__.return_value=result
            result.status_code=status
            result.raw.read.return_value=json.dumps(value).encode('utf-8')
            return result
        with patch('support_ai.mcp_http.requests.Session') as session:
            session.return_value.headers={}
            session.return_value.post.side_effect=[
                response({'jsonrpc':'2.0','id':1,'result':{'protocolVersion':'2025-06-18'}}),response({},202),
                response({'jsonrpc':'2.0','id':2,'result':{'tools':[{'name':'validate_categories'}]}}),
                response({'jsonrpc':'2.0','id':3,'result':{'structuredContent':{}}})]
            transport=HttpMcpTransport({'TEA_SAAS_AGENT_GRANT':'synthetic-private-grant'})
            transport.request('tools/call',{'name':'validate_categories','arguments':{'categories':[]}})
            self.assertFalse(session.return_value.trust_env)
            self.assertEqual(session.return_value.headers['X-Tea-Saas-Agent-Grant'],'synthetic-private-grant')
            bodies=[call.kwargs['json'] for call in session.return_value.post.call_args_list]
            self.assertNotIn('synthetic-private-grant',json.dumps(bodies))
            self.assertNotIn(TOKEN,json.dumps(bodies))
            self.assertTrue(all(not call.kwargs['allow_redirects'] for call in session.return_value.post.call_args_list))
            transport.close()

    def test_remote_or_credentialled_urls_are_rejected_before_network_access(self):
        with patch('support_ai.mcp_http.requests.Session') as session:
            for value in ('https://remote.invalid/mcp','http://127.0.0.1:18082/mcp?redirect=x',
                          'http://user:password@127.0.0.1:18082/mcp'):
                with override_settings(SUPPORT_MCP_URL=value):
                    with self.assertRaises(McpServiceError) as caught:
                        HttpMcpTransport({'TEA_SAAS_AGENT_GRANT':'synthetic'})
                    self.assertEqual(caught.exception.code,'BACKEND_NOT_CONFIGURED')
            session.assert_not_called()
