"""Run with the Django interpreter: real MCP processes, disposable synthetic DBs."""
import json
import os
from pathlib import Path
import tempfile
import uuid
import subprocess
import time
from contextlib import contextmanager, ExitStack


@contextmanager
def resident_service(root, scratch):
    """Owned test service only; ready before requests, graceful EOF shutdown."""
    import socket
    import requests
    from django.conf import settings
    from django.test import override_settings
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0))
        port=listener.getsockname()[1]
    token=uuid.uuid4().hex+uuid.uuid4().hex
    environment=dict(os.environ,TEA_SAAS_PYTHON=os.sys.executable,SUPPORT_MCP_SERVICE_TOKEN=token)
    log=(scratch/'resident-service.log').open('wb')
    process=subprocess.Popen([settings.SUPPORT_MCP_PYTHON,'-u','-m','tools.tea_saas_mcp.resident',
        '--port',str(port),'--workers','2','--watch-stdin'],cwd=root,env=environment,
        stdin=subprocess.PIPE,stdout=log,stderr=log,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0) if os.name=='nt' else 0)
    client=requests.Session();client.trust_env=False
    base='http://127.0.0.1:'+str(port)
    try:
        deadline=time.monotonic()+40
        while True:
            if process.poll() is not None:
                raise RuntimeError('Resident test service failed startup')
            try:
                response=client.get(base+'/health',timeout=.5)
                if response.status_code==200 and response.json()['workers']==2:
                    break
            except requests.RequestException:
                pass
            if time.monotonic()>=deadline:
                raise RuntimeError('Resident test service not ready')
            time.sleep(.2)
        with override_settings(SUPPORT_MCP_TRANSPORT='http',SUPPORT_MCP_URL=base+'/mcp',SUPPORT_MCP_SERVICE_TOKEN=token):
            yield client,base,token
    finally:
        client.close()
        process.stdin.close()
        try:
            process.wait(timeout=12)
        except subprocess.TimeoutExpired:
            if os.name=='nt':
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True,check=True)
            else:
                process.kill()
            process.wait(timeout=5)
        log.close()


@contextmanager
def mysql_database():
    """A new labelled container, existing image only, no mounts or business credentials."""
    import MySQLdb
    nonce = uuid.uuid4().hex[:12]
    name = 'tea-saas-mcp-test-' + nonce
    password = uuid.uuid4().hex
    environment = dict(os.environ, MYSQL_PASSWORD=password, MYSQL_ROOT_PASSWORD=uuid.uuid4().hex)
    result = subprocess.run(['docker','run','--rm','--detach','--pull=never','--name',name,
        '--label','tea-saas-mcp-fixture='+nonce,'--publish','127.0.0.1::3306',
        '--env','MYSQL_ROOT_PASSWORD','--env','MYSQL_PASSWORD','--env','MYSQL_DATABASE=test_mcp',
        '--env','MYSQL_USER=mcp_fixture','mysql:8.0.46'],env=environment,capture_output=True,check=True)
    container_id = result.stdout.decode().strip()
    try:
        state = json.loads(subprocess.check_output(['docker','inspect',container_id]))[0]
        assert state['Config']['Labels']['tea-saas-mcp-fixture'] == nonce
        port = int(state['NetworkSettings']['Ports']['3306/tcp'][0]['HostPort'])
        deadline = time.monotonic() + 60
        while True:
            try:
                connection = MySQLdb.connect(host='127.0.0.1',port=port,user='mcp_fixture',passwd=password,
                                             db='test_mcp',connect_timeout=2)
                connection.close()
                break
            except MySQLdb.Error:
                if time.monotonic() >= deadline:
                    raise RuntimeError('Disposable MySQL did not become ready') from None
                time.sleep(1)
        yield port, password
    finally:
        state = json.loads(subprocess.check_output(['docker','inspect',container_id]))[0]
        assert state['Config']['Labels']['tea-saas-mcp-fixture'] == nonce and state['Name'] == '/' + name
        subprocess.run(['docker','rm','--force','--volumes',container_id],capture_output=True,check=True)


@contextmanager
def postgres_database(database):
    import re
    import psycopg2
    from psycopg2 import sql
    name = database['NAME']
    assert re.fullmatch(r'test_mcp_[0-9a-f]{12}', name)
    connection = psycopg2.connect(dbname='postgres', user=database['USER'], password=database['PASSWORD'],
        host=database['HOST'], port=database['PORT'], connect_timeout=5)
    connection.autocommit = True
    created = False
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
        created = True
        yield
    finally:
        if created:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(name)))
        connection.close()


def run():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--postgres', action='store_true')
    parser.add_argument('--mysql', action='store_true')
    parser.add_argument('--profile-output',type=Path,help='Write content-free cold/reused-session timing evidence')
    parser.add_argument('--local-models',action='store_true',help='Use loopback Ollama/reranker with synthetic knowledge only')
    parser.add_argument('--resident',action='store_true',help='Prewarm the independent MCP HTTP service')
    arguments = parser.parse_args()
    if arguments.local_models and (not arguments.postgres or not arguments.profile_output):
        parser.error('--local-models requires --postgres and --profile-output')
    if arguments.local_models:
        from urllib.parse import urlparse
        for value in (os.getenv('AI_OLLAMA_BASE_URL','http://127.0.0.1:11434'),
                      os.getenv('AI_RERANK_BASE_URL','http://127.0.0.1:18081')):
            parsed=urlparse(value)
            if parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or parsed.username:
                parser.error('Synthetic profiling permits loopback local model endpoints only')
    root = Path(__file__).resolve().parents[2]
    scratch = root / '.scratch' / 'mcp-integration'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='run-', dir=str(scratch)) as folder, ExitStack() as resources:
        os.environ.update(DJANGO_SETTINGS_MODULE='tools.tea_saas_mcp.test_settings',
            TEA_SAAS_MCP_TEST_DB=str(Path(folder) / 'business.sqlite3'),
            TEA_SAAS_MCP_TEST_AI_DB=str(Path(folder) / 'knowledge.sqlite3'),
            SUPPORT_API_KEY='', SUPPORT_RAG_RETRY_ENABLED='false', SUPPORT_RAG_REWRITE_CALLS='0')
        if not arguments.local_models:
            os.environ['AI_OLLAMA_BASE_URL']='http://127.0.0.1:1'
        mysql_port = None
        if arguments.mysql:
            mysql_port, mysql_password = resources.enter_context(mysql_database())
            os.environ.update(TEA_SAAS_MCP_TEST_MYSQL_PORT=str(mysql_port),
                              TEA_SAAS_MCP_TEST_MYSQL_PASSWORD=mysql_password)
        if arguments.postgres:
            os.environ.update(DJANGO_SETTINGS_MODULE='tools.tea_saas_mcp.agent_pg_test_settings',
                              TEA_SAAS_MCP_TEST_PG='test_mcp_' + uuid.uuid4().hex[:12])
        # No configured business DB is opened. Both aliases are asserted below
        # before Django's migration command is allowed to run.
        import django
        django.setup()
        from django.conf import settings
        from django.db import connections
        from django.core.management import call_command
        if arguments.postgres:
            resources.enter_context(postgres_database(settings.DATABASES['ai_storage']))
        resources.callback(connections.close_all)
        for alias in ('default','ai_storage'):
            database = settings.DATABASES[alias]
            if alias == 'default' and arguments.mysql:
                assert database['ENGINE'] == 'django.db.backends.mysql' and database['NAME'] == 'test_mcp'
                assert database['PORT'] == mysql_port and database['USER'] == 'mcp_fixture'
            elif alias == 'ai_storage' and arguments.postgres:
                assert database['NAME'] == os.environ['TEA_SAAS_MCP_TEST_PG']
            else:
                assert database['ENGINE'] == 'django.db.backends.sqlite3'
                assert Path(database['NAME']).resolve().parent == Path(folder).resolve()
            call_command('migrate', database=alias, verbosity=0, interactive=False)

        from users.models import UserProfile
        from goods.models import Catalog, SPU, SKU
        from orders.models import OrderInfo
        from ai_storage.models import BuyerMemory, KnowledgeDocument, KnowledgeChunk
        from support_ai.models import SupportConversation, SupportTurn
        from support_ai.mcp_client import AgentDataAccess, McpServiceError
        from support_ai.mcp_testing import config
        from support_ai.order_queries import OrderQueryContext
        from support_ai.order_contracts import rule_order_query
        from support_ai.contracts import RecommendationIntent
        from support_ai.planning import TaskStep
        from support_ai.execution import ToolResult

        buyer = UserProfile.objects.create(username='mcpbuyer', user_type='customer', is_active=True)
        other = UserProfile.objects.create(username='mcpother', user_type='customer', is_active=True)
        category = Catalog.objects.create(name='绿茶')
        merchant = UserProfile.objects.create(username='mcp-synthetic-merchant', user_type='merchant', is_active=True)
        product = SPU.objects.create(name='合成协议商品', catalog=category, merchant=merchant)
        sku = SKU.objects.create(name='50克装', spu=product, price='12.30', cost_price='1', market_price='15', stock=10)
        for index in range(4):
            OrderInfo.objects.create(order_id='SYNTHETIC-PRIVATE-{}'.format(index), user_profile=buyer,
                total_amount='12.30', total_count=1, freight='0', status=1, receiver='Synthetic',
                address='Synthetic', receiver_mobile='00000000000', tag='Test')
        BuyerMemory.objects.create(owner_id=buyer.pk, preferences={'categories':['绿茶']})
        if arguments.postgres:
            for key, visibility, status, owner in (
                    ('public','public','published',None), ('own','private','published',buyer.pk),
                    ('foreign','private','published',other.pk), ('draft','public','draft',None)):
                document = KnowledgeDocument.objects.create(source_key=key, title=key, visibility=visibility,
                    status=status, owner_id=owner)
                KnowledgeChunk.objects.create(document=document, ordinal=1, text='green tea brewing ' + key)
        if arguments.local_models:
            # Synthetic vectors only: this measures runtime, not ranking quality,
            # and does not warm the model by embedding fixtures before the trace.
            from ai_storage.models import EmbeddingSpace
            space=EmbeddingSpace.objects.create(key=settings.AI_EMBEDDING_SPACE_KEY,provider='synthetic',
                model=settings.AI_OLLAMA_MODEL,revision='timing-fixture',dimensions=1024)
            KnowledgeChunk.objects.update(embedding=[1.]*1024,embedding_space=space)
        conversation = SupportConversation.objects.create(user=buyer, revision=1)
        SupportTurn.objects.create(user=buyer, conversation=conversation, sequence=1, request_id=uuid.uuid4(),
            request_hash='synthetic', user_text='推荐绿茶', answer='合成历史', intent='recommendation', response={})
        count = 0
        def access(message='推荐绿茶', **extra):
            return AgentDataAccess(config=config(), message=message, owner_id=buyer.pk, **extra)

        resident=None
        if arguments.resident:
            resident=resources.enter_context(resident_service(root,Path(folder)))

        if arguments.profile_output:
            from dataclasses import replace
            from support_ai.telemetry import observe_agent
            from support_ai.models import AgentSpan
            from support_ai.trace_analysis import analyze_spans
            profiles=[]
            profile_config=replace(config(),telemetry_enabled=True,rerank_enabled=arguments.local_models)
            # stdio: fresh processes; resident: fresh leases on already warm
            # workers. Each repeats the query to distinguish session/cache cost.
            for number in range(2):
                with observe_agent(profile_config) as observation:
                    with AgentDataAccess(config=profile_config,message='green tea brewing',owner_id=buyer.pk) as client:
                        first=client.search('green tea brewing')
                        second=client.search('green tea brewing')
                        assert first and second
                        assert {x['source_title'] for x in first}=={'public','own'}
                    trace_id=observation.trace_id
                rows=list(AgentSpan.objects.filter(trace_id=trace_id).values(
                    'name','span_id','parent_span_id','started_at','duration_ms','status','attributes'))
                names={row['name'] for row in rows}
                required=({'mcp.session.connect'} if arguments.resident else {'mcp.sdk.startup','mcp.backend.ready'})
                assert required | {'mcp.backend.call','knowledge.retrieve'} <= names,names
                if arguments.resident:
                    assert not {'mcp.sdk.spawn','mcp.backend.spawn','mcp.backend.ready'} & names
                assert all(row['attributes'].get('agent.mcp.telemetry','complete')=='complete' for row in rows)
                root_row=next(row for row in rows if row['name']=='support.chat')
                assert root_row['attributes']['agent.retrieval.hits']==len(first)+len(second)
                assert root_row['attributes']['agent.llm.calls']==0
                profiles.append(dict(request=number+1,trace_id=trace_id,**analyze_spans(rows)))
            output=arguments.profile_output.resolve()
            output.parent.mkdir(parents=True,exist_ok=True)
            startup=(resident[0].get(resident[1]+'/health',timeout=5).json() if resident else None)
            output.write_text(json.dumps(dict(synthetic=True,local_models=arguments.local_models,
                transport='resident' if arguments.resident else 'stdio',service_startup=startup,
                external_provider_calls=0,vector_quality='synthetic vectors; no retrieval quality claim',
                profiles=profiles),ensure_ascii=False,indent=2,default=str),encoding='utf-8')

        with access(conversation=conversation) as client:
            assert len(client.history()) == 1
            assert client.preferences()['preferences']['categories'] == ['绿茶']
            assert client.call('validate_categories',categories=['绿茶'])['data']['valid']
            assert client.call('resolve_product',name=sku.name,product_name=product.name)['data']['sku_id'] == sku.pk
            assert client.call('get_product_details',sku_id=sku.pk)['data']['price'] == '12.30'
            intent = RecommendationIntent(action='SEARCH')
            found = client.call('search_products',intent=intent)['data']
            assert found['recommendations'][0]['sku_id'] == sku.pk
            grouped = client.call('search_products',intent=intent,options={'mode':'by_category'})['data']
            assert grouped['recommendation_groups']
            step = TaskStep(id='s2',intent='recommendation_explanation',tool='explain_recommendations',
                            request='解释推荐理由',product_from='s1',depends_on=['s1'])
            explained = client.call('explain_recommendations',step=step,
                completed={'s1':ToolResult(step_id='s1',tool='recommend_products',status='success',data=found)})
            assert explained['data']['explained_products'][0]['sku_id'] == sku.pk
            count += 8
            # SQLite cannot serve PostgreSQL full text. Its failure must stay a
            # technical error, and must not poison the following catalog call.
            if arguments.postgres:
                evidence = client.search('green tea brewing')
                assert {row['source_title'] for row in evidence} == {'public','own'}, evidence
                client.search('green tea brewing public')
                assert len(client.audit) == 2
            else:
                try:
                    client.search('合成不存在知识')
                except McpServiceError as exc:
                    assert exc.code == 'SERVICE_UNAVAILABLE'
            assert client.call('get_product_details',sku_id=sku.pk)['status'] == 'success'
            count += 2

        text = '推荐总价为24.60元的茶'
        with access(text) as client:
            intent = RecommendationIntent(action='SEARCH', required={'price_basis':'total','budget_max':'24.60'}, evidence=[
                {'field':'required.price_basis','value':'total','source':'CURRENT','quote':text},
                {'field':'required.budget_max','value':'24.60','source':'CURRENT','quote':text}])
            bundle = client.call('recommend_bundle',intent=intent)['data']
            assert bundle['recommendation_bundles'][0]['subtotal'] == '24.60'
            count += 1

        context = OrderQueryContext(owner_id=buyer.pk)
        with access('查询最近订单',order_context=context) as client:
            orders = client.call('get_order_status',query=rule_order_query('查询最近订单'),request='查询最近订单')
            assert len(orders['data']['orders']) == 3
            assert 'SYNTHETIC-PRIVATE' not in json.dumps(orders)
            assert context.navigation_tokens
            count += 1
        with AgentDataAccess(config=config(),message='查询偏好',owner_id=other.pk) as client:
            assert client.preferences() is None
            if arguments.postgres:
                assert {row['source_title'] for row in client.search('green tea brewing')} == {'public','foreign'}
            count += 1

        from django.test import Client
        from tea_saas.utils import jwt_encode
        http = Client()
        auth = {'HTTP_AUTHORIZATION':'Bearer ' + jwt_encode({'id':buyer.pk})}
        request = {'message':'查询最近订单','request_id':str(uuid.uuid4())}
        response = http.post('/v1/support/chat/',data=json.dumps(request),content_type='application/json',**auth)
        assert response.status_code == 200, response.content.decode()
        assert len(response.json()['order_result']['orders']) == 3
        repeated = http.post('/v1/support/chat/',data=json.dumps(request),content_type='application/json',**auth)
        assert repeated.json() == response.json()
        from support_ai.preview import PreviewSession
        session = PreviewSession(user=buyer, log_dir=Path(folder) / 'preview')
        assert len(session.ask('查询最近订单')['response']['order_result']['orders']) == 3
        count += 3
        if resident:
            # Different buyers simultaneously occupy distinct request sessions;
            # repeated grants cannot revive an already closed DataSession.
            from concurrent.futures import ThreadPoolExecutor
            def buyer_read(user):
                with AgentDataAccess(config=config(),message='本人偏好',owner_id=user.pk) as client:
                    return client.preferences(),client.environment['TEA_SAAS_AGENT_GRANT']
            with ThreadPoolExecutor(max_workers=2) as executor:
                first,second=list(executor.map(buyer_read,[buyer,other]))
            assert first[0]['preferences']['categories']==['绿茶'] and second[0] is None
            http_client,base,token=resident
            denied=http_client.post(base+'/mcp',json={'jsonrpc':'2.0','id':1,'method':'tools/list','params':{}},
                headers={'Authorization':'Bearer '+token,'X-Tea-Saas-Agent-Grant':first[1],
                         'Accept':'application/json, text/event-stream'},timeout=5)
            assert denied.status_code==403
            status=http_client.get(base+'/health',timeout=5).json()
            assert status['workers']==2 and status['active_sessions']==0 and status['available']==2,status
            assert status['worker_starts']==2,status
            count+=3
        connections.close_all()
        summary = {'status':'passed','checks':count,
                   'databases':('disposable MySQL' if arguments.mysql else 'disposable SQLite') + (' + PostgreSQL' if arguments.postgres else ' + SQLite knowledge'),
                   'transport':('resident HTTP MCP SDK -> prewarmed Django pool' if arguments.resident else
                                'real stdio MCP SDK -> persistent Django backend'),'provider_calls':0}
    print(json.dumps(dict(summary, cleanup='completed')))


if __name__ == '__main__':
    run()
