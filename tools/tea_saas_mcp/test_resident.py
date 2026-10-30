"""Resident protocol/authentication and exclusive worker lifecycle tests."""
import asyncio
import sys
import time
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from .resident import create_app
from .resident_pool import WorkerPool, PoolError


TOKEN='synthetic-service-key-not-a-real-secret-000000'


class FakePool:
    def __init__(self):
        self.calls=[]

    async def start(self):
        pass

    async def stop(self):
        pass

    def health(self):
        return {'status':'ready'}

    async def open(self,grant):
        self.calls.append(('open',grant))

    async def release(self,grant):
        self.calls.append(('close',grant))

    async def call(self,grant,name,arguments):
        self.calls.append(('call',grant,name))
        return {'schema_version':'1.0','status':'success','data':{'sku_id':1},
                'observed_at':'2026-10-29T00:00:00Z','limitations':[]}


class ResidentProtocolTests(unittest.TestCase):
    def headers(self,grant='synthetic-grant'):
        return {'Authorization':'Bearer '+TOKEN,'X-Tea-Saas-Agent-Grant':grant,
                'Accept':'application/json, text/event-stream'}

    def test_stateless_protocol_keeps_grant_in_trusted_headers_and_tools_unchanged(self):
        pool=FakePool()
        with TestClient(create_app(pool,TOKEN),base_url='http://127.0.0.1:18082') as client:
            headers=self.headers()
            response=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':1,'method':'initialize',
                'params':{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'test','version':'1'}}})
            self.assertEqual(response.status_code,200,response.text)
            headers['MCP-Protocol-Version']=response.json()['result']['protocolVersion']
            listed=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}})
            self.assertIn('get_order_status',[t['name'] for t in listed.json()['result']['tools']])
            result=client.post('/mcp',headers=headers,json={'jsonrpc':'2.0','id':3,'method':'tools/call',
                'params':{'name':'get_product_details','arguments':{'sku_id':1}}})
            self.assertEqual(result.json()['result']['structuredContent']['data'],{'sku_id':1})
            self.assertNotIn('synthetic-grant',result.text)
            self.assertIn(('call','synthetic-grant','get_product_details'),pool.calls)
            self.assertEqual(client.delete('/agent-session',headers=headers).status_code,204)
            self.assertEqual(pool.calls[-1],('close','synthetic-grant'))

    def test_missing_service_key_browser_origin_and_untrusted_grant_never_reach_pool(self):
        pool=FakePool()
        with TestClient(create_app(pool,TOKEN),base_url='http://127.0.0.1:18082') as client:
            self.assertEqual(client.get('/health').status_code,200)
            for headers in ({},dict(self.headers(),Authorization='Bearer wrong'),
                            dict(self.headers(),Origin='https://untrusted.invalid')):
                self.assertIn(client.post('/mcp',headers=headers,json={}).status_code,(401,403))
            self.assertFalse(pool.calls)


class FakeWorker:
    def __init__(self,python):
        self.healthy=False
        self.grant=None

    async def start(self):
        self.healthy=True

    async def stop(self):
        self.healthy=False

    async def rpc(self,message,timeout=35):
        if message['action']=='open':
            assert self.grant is None
            if message['grant']=='invalid':
                return {'status':'error'}
            self.grant=message['grant']
            return {'session_ready':1,'expires_at':time.time()+120}
        self.grant=None
        return {'session_closed':1}


class ResidentPoolTests(unittest.IsolatedAsyncioTestCase):
    async def pool(self,size=2,lease_seconds=120):
        mocked=patch('tools.tea_saas_mcp.resident_pool.Worker',FakeWorker)
        mocked.start()
        self.addCleanup(mocked.stop)
        pool=WorkerPool(sys.executable,size=size,acquire_timeout=.01,lease_seconds=lease_seconds)
        await pool.start()
        self.addAsyncCleanup(pool.stop)
        return pool

    async def test_preloaded_workers_are_reused_but_request_state_is_not(self):
        pool=await self.pool()
        original=set(pool.workers)
        a,b=await asyncio.gather(pool.open('buyer-a'),pool.open('buyer-b'))
        self.assertIsNot(a.worker,b.worker)
        self.assertIs(await pool.open('buyer-a'),a)
        with self.assertRaises(PoolError) as caught:
            await pool.open('buyer-c')
        self.assertEqual(caught.exception.code,'BACKEND_BUSY')
        await pool.release('buyer-a')
        c=await pool.open('buyer-c')
        self.assertIs(c.worker,a.worker)
        self.assertEqual(c.worker.grant,'buyer-c')
        self.assertEqual(set(pool.workers),original)

    async def test_invalid_grant_releases_slot_and_closed_or_expired_leases_cannot_call(self):
        pool=await self.pool(size=1)
        with self.assertRaises(PoolError):
            await pool.open('invalid')
        self.assertEqual(pool.available.qsize(),1)
        lease=await pool.open('valid')
        lease.expires=time.monotonic()-1
        self.assertEqual((await pool.call('valid','get_order_status',{}))['error_code'],'ACCESS_DENIED')
        await pool.release('valid')
        self.assertEqual((await pool.call('valid','get_order_status',{}))['error_code'],'ACCESS_DENIED')

    async def test_supervision_replaces_dead_process_without_reviving_its_request(self):
        pool=await self.pool(size=1)
        old=await pool.open('old-request')
        old.worker.healthy=False
        await asyncio.sleep(1.1)
        self.assertNotIn(old.worker,pool.workers)
        self.assertEqual(pool.available.qsize(),1)
        with self.assertRaises(PoolError):
            await pool.open('old-request')
        fresh=await pool.open('fresh-request')
        self.assertIsNot(fresh.worker,old.worker)
        await pool.release('old-request')
        self.assertTrue(fresh.worker.healthy)

    async def test_lost_client_lease_expires_and_reclaims_capacity(self):
        pool=await self.pool(size=1,lease_seconds=.01)
        old=await pool.open('lost-client')
        await asyncio.sleep(1.1)
        self.assertFalse(pool.leases)
        self.assertFalse(old.worker.healthy)
        self.assertEqual(pool.available.qsize(),1)


if __name__=='__main__':
    unittest.main()
