"""Loopback MCP Streamable HTTP service, prewarmed before it accepts requests."""
import asyncio
import hmac
import json
import logging
import os
import re
from contextlib import asynccontextmanager

from jsonschema import validate, ValidationError
from mcp import types
from mcp.server import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.applications import Starlette
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .resident_pool import WorkerPool, PoolError
from .server import PRIVATE_SCHEMAS, PRIVATE_OUTPUT, private_failure

GRANT_HEADER = 'x-tea-saas-agent-grant'


def create_app(pool, service_token):
    if not isinstance(service_token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',service_token):
        raise ValueError('Service token must be configured')
    server = Server('tea-saas-resident-agent-data')
    import uuid
    instance=os.getenv('TEA_SAAS_MCP_INSTANCE') or uuid.uuid4().hex
    manager = StreamableHTTPSessionManager(server, json_response=True, stateless=True,
        security_settings=TransportSecuritySettings(enable_dns_rebinding_protection=True,
            allowed_hosts=['127.0.0.1:*','localhost:*','[::1]:*']))

    @server.list_tools()
    async def list_tools():
        return [types.Tool(name=name,description=entry['description'],inputSchema=entry['input'],
            outputSchema=PRIVATE_OUTPUT,annotations=types.ToolAnnotations(readOnlyHint=True,
                destructiveHint=False,idempotentHint=True,openWorldHint=False))
            for name,entry in PRIVATE_SCHEMAS.items()]

    @server.call_tool()
    async def call_tool(name, arguments):
        if name not in PRIVATE_SCHEMAS:
            result = private_failure('UNKNOWN_TOOL')
        else:
            try:
                validate(arguments,PRIVATE_SCHEMAS[name]['input'])
                grant = server.request_context.request.headers.get(GRANT_HEADER,'')
                result = await pool.call(grant,name,arguments)
            except ValidationError:
                result = private_failure('INVALID_ARGUMENT')
        return types.CallToolResult(content=[types.TextContent(type='text',text=json.dumps(result,ensure_ascii=False))],
                                    structuredContent=result,isError=result['status']=='error')

    @asynccontextmanager
    async def lifespan(app):
        try:
            await pool.start()
            async with manager.run():
                yield
        finally:
            await pool.stop()

    async def health(request):
        value=pool.health()
        value['instance_id']=instance
        return JSONResponse(value,status_code=200 if value['status']=='ready' else 503)

    async def close_session(request):
        await pool.release(request.headers[GRANT_HEADER])
        return Response(status_code=204)

    class McpEndpoint:
        async def __call__(self,scope,receive,send):
            if scope['method'] != 'POST':
                await Response(status_code=405)(scope,receive,send)
                return
            headers=dict(scope['headers'])
            grant=headers[GRANT_HEADER.encode()].decode('ascii')
            try:
                await pool.open(grant)
            except PoolError as exc:
                await JSONResponse({'error_code':exc.code},status_code=503 if exc.code in (
                    'BACKEND_BUSY','SERVICE_UNAVAILABLE','BACKEND_TIMEOUT') else 403)(scope,receive,send)
                return
            await manager.handle_request(scope,receive,send)

    app=Starlette(routes=[Route('/health',health),Route('/mcp',McpEndpoint(),methods=['POST']),
                          Route('/agent-session',close_session,methods=['DELETE'])],lifespan=lifespan)

    class AuthenticatedApp:
        async def __call__(self,scope,receive,send):
            if scope['type']=='http' and scope['path']!='/health':
                headers=dict(scope['headers'])
                authorization=headers.get(b'authorization',b'')
                grant=headers.get(GRANT_HEADER.encode(),b'')
                if not hmac.compare_digest(authorization,b'Bearer '+service_token.encode('ascii')):
                    await JSONResponse({'error_code':'ACCESS_DENIED'},status_code=401)(scope,receive,send)
                    return
                if b'origin' in headers or not 1 <= len(grant) <= 65536:
                    await JSONResponse({'error_code':'ACCESS_DENIED'},status_code=403)(scope,receive,send)
                    return
                try:
                    grant.decode('ascii')
                except UnicodeDecodeError:
                    await Response(status_code=403)(scope,receive,send)
                    return
            await app(scope,receive,send)
    return AuthenticatedApp()


def main():
    import argparse
    import sys
    if sys.version_info[:2] != (3,13):
        raise SystemExit('The managed MCP service requires Python 3.13.')
    import uvicorn
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=18082)
    parser.add_argument('--workers',type=int,default=2)
    parser.add_argument('--watch-stdin',action='store_true')
    args=parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error('Invalid loopback port')
    # MCP internal logs may contain arbitrary invalid argument strings. Export
    # only our safe status DTOs and existing content-free application tracing.
    logging.getLogger('mcp').setLevel(logging.CRITICAL)
    pool=WorkerPool(os.environ.get('TEA_SAAS_PYTHON',''),size=args.workers)
    app=create_app(pool,os.environ.get('SUPPORT_MCP_SERVICE_TOKEN',''))
    service=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=args.port,access_log=False,log_level='warning'))
    if args.watch_stdin:
        import sys
        import threading
        def parent_closed():
            sys.stdin.buffer.read()
            service.should_exit=True
        threading.Thread(target=parent_closed,daemon=True).start()
    service.run()


if __name__=='__main__':
    main()
