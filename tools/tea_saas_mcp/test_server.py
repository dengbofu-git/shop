"""Run with the separate MCP Python; no business databases or models."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.memory import create_connected_server_and_client_session

from tools.tea_saas_mcp import server as adapter


class AdapterTests(unittest.IsolatedAsyncioTestCase):
    async def test_invalid_ids_never_spawn_backend(self):
        with patch.object(adapter.asyncio, 'create_subprocess_exec') as spawn:
            for value in (True, '1', 1.0, 0, -1, 2147483648):
                self.assertEqual((await adapter.read_details(value))['error_code'], 'INVALID_ARGUMENT')
            spawn.assert_not_called()

    async def test_fixed_command_and_structured_success(self):
        payload = {'schema_version': '1.0', 'status': 'success', 'data': {'sku_id': 7},
                   'observed_at': '2026-10-18T12:00:00+08:00', 'limitations': []}
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (json.dumps(payload).encode(), b'not exposed')
        with patch.dict(os.environ, {'TEA_SAAS_PYTHON': sys.executable}), \
                patch.object(adapter.asyncio, 'create_subprocess_exec', return_value=process) as spawn:
            self.assertEqual(await adapter.read_details(7), payload)
        args = spawn.call_args.args
        self.assertEqual(args[0], sys.executable)
        self.assertEqual(args[4:], ('mcp_product_details', '--sku-id', '7', '--no-color'))
        self.assertNotIn('shell', spawn.call_args.kwargs)

    async def test_timeout_kills_backend_and_sanitizes_error(self):
        process = AsyncMock()
        process.returncode = None
        process.kill = unittest.mock.Mock()
        async def timeout(awaitable, **kwargs):
            awaitable.close()
            raise asyncio.TimeoutError
        with patch.dict(os.environ, {'TEA_SAAS_PYTHON': sys.executable}), \
                patch.object(adapter.asyncio, 'create_subprocess_exec', return_value=process), \
                patch.object(adapter.asyncio, 'wait_for', side_effect=timeout):
            result = await adapter.read_details(1)
        process.kill.assert_called_once()
        self.assertEqual(result['error_code'], 'BACKEND_TIMEOUT')

    async def test_failure_and_malformed_output_do_not_expose_stderr(self):
        process = AsyncMock()
        process.communicate.return_value = (b'{broken', b'password=secret')
        for returncode in (0, 1):
            process.returncode = returncode
            with patch.dict(os.environ, {'TEA_SAAS_PYTHON': sys.executable}), \
                    patch.object(adapter.asyncio, 'create_subprocess_exec', return_value=process):
                result = await adapter.read_details(1)
            self.assertEqual(result['status'], 'error')
            self.assertNotIn('secret', json.dumps(result))

    async def test_cancellation_reaps_backend(self):
        process = AsyncMock()
        process.returncode = None
        process.kill = unittest.mock.Mock()
        process.communicate.side_effect = [asyncio.CancelledError, (b'', b'')]
        with patch.dict(os.environ, {'TEA_SAAS_PYTHON': sys.executable}), \
                patch.object(adapter.asyncio, 'create_subprocess_exec', return_value=process):
            with self.assertRaises(asyncio.CancelledError):
                await adapter.read_details(1)
        process.kill.assert_called_once()

    async def test_invalid_backend_envelope_is_not_forwarded(self):
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (
            b'{"schema_version":"1.0","status":"success","data":null,"internal_secret":"hidden"}', b'')
        with patch.dict(os.environ, {'TEA_SAAS_PYTHON': sys.executable}), \
                patch.object(adapter.asyncio, 'create_subprocess_exec', return_value=process):
            result = await adapter.read_details(1)
        self.assertEqual(result['error_code'], 'INVALID_BACKEND_RESPONSE')
        self.assertNotIn('hidden', json.dumps(result))

    async def test_protocol_success_no_match_and_unknown_tool(self):
        async with create_connected_server_and_client_session(adapter.server) as client:
            for status in ('success', 'no_match'):
                payload = {'schema_version': '1.0', 'status': status,
                           'data': {'sku_id': 7} if status == 'success' else None,
                           'observed_at': '2026-10-18T12:00:00+08:00', 'limitations': []}
                with patch.object(adapter, 'read_details', return_value=payload):
                    result = await client.call_tool('get_product_details', {'sku_id': 7})
                self.assertFalse(result.isError)
                self.assertEqual(result.structuredContent, payload)
                self.assertEqual(json.loads(result.content[0].text), payload)
            unknown = await client.call_tool('execute_sql', {'sql': 'select *'})
            self.assertTrue(unknown.isError)
            self.assertEqual(unknown.structuredContent['error_code'], 'UNKNOWN_TOOL')

    @unittest.skipUnless(os.environ.get('TEA_SAAS_TEST_PYTHON'), 'Set TEA_SAAS_TEST_PYTHON for isolated Django integration')
    async def test_stdio_to_real_django_command_with_synthetic_sqlite(self):
        business_python = os.environ['TEA_SAAS_TEST_PYTHON']
        with tempfile.TemporaryDirectory(prefix='tea_saas-mcp-test-') as folder:
            env = dict(os.environ, TEA_SAAS_PYTHON=business_python,
                       DJANGO_SETTINGS_MODULE='tools.tea_saas_mcp.test_settings',
                       TEA_SAAS_MCP_TEST_DB=str(Path(folder) / 'catalog.sqlite3'))
            setup = (
                "import django; django.setup(); from django.core.management import call_command; "
                "call_command('migrate',verbosity=0,interactive=False); "
                "from goods.models import Catalog,SPU,SKU; "
                "c=Catalog.objects.create(name='绿茶'); s=SPU.objects.create(name='合成测试茶',catalog=c); "
                "p=SKU.objects.create(name='50克装',caption='',spu=s,price='12.30',cost_price='1',market_price='15',stock=7); "
                "print(p.pk)"
            )
            fixture = subprocess.run([business_python, '-X', 'utf8', '-c', setup], cwd=adapter.ROOT,
                                     env=env, capture_output=True, check=True, timeout=30)
            sku_id = int(fixture.stdout.decode('utf-8').strip())
            params = StdioServerParameters(command=sys.executable,
                                          args=[str(adapter.ROOT / 'tools/tea_saas_mcp/server.py')], env=env)
            async with stdio_client(params) as (reader, writer):
                async with ClientSession(reader, writer) as client:
                    await client.initialize()
                    found = await client.call_tool('get_product_details', {'sku_id': sku_id})
                    self.assertFalse(found.isError)
                    self.assertEqual(found.structuredContent['data']['price'], '12.30')
                    self.assertEqual(found.structuredContent['data']['available_stock'], 7)
                    update = ("import django; django.setup(); from goods.models import SKU; "
                              "SKU.objects.update(stock=0)")
                    subprocess.run([business_python, '-X', 'utf8', '-c', update], cwd=adapter.ROOT,
                                   env=env, capture_output=True, check=True, timeout=15)
                    exhausted = await client.call_tool('get_product_details', {'sku_id': sku_id})
                    self.assertFalse(exhausted.isError)
                    self.assertEqual(exhausted.structuredContent['status'], 'no_match')

    async def test_real_stdio_initialize_list_and_error_call(self):
        env = dict(os.environ, TEA_SAAS_PYTHON='')
        params = StdioServerParameters(command=sys.executable, args=[str(adapter.ROOT / 'tools/tea_saas_mcp/server.py')], env=env)
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as client:
                await client.initialize()
                tools = (await client.list_tools()).tools
                self.assertEqual([tool.name for tool in tools], ['get_product_details'])
                self.assertTrue(tools[0].annotations.readOnlyHint)
                missing = await client.call_tool('get_product_details', {'sku_id': 7})
                self.assertTrue(missing.isError)
                self.assertEqual(missing.structuredContent['error_code'], 'BACKEND_NOT_CONFIGURED')
                for arguments in ({'sku_id': True}, {'sku_id': 1.0}, {'sku_id': 0}, {'sku_id': 1, 'user_id': 8}):
                    rejected = await client.call_tool('get_product_details', arguments)
                    self.assertTrue(rejected.isError)


if __name__ == '__main__':
    unittest.main()
