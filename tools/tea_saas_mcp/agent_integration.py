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
    arguments = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    scratch = root / '.scratch' / 'mcp-integration'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='run-', dir=str(scratch)) as folder, ExitStack() as resources:
        os.environ.update(DJANGO_SETTINGS_MODULE='tools.tea_saas_mcp.test_settings',
            TEA_SAAS_MCP_TEST_DB=str(Path(folder) / 'business.sqlite3'),
            TEA_SAAS_MCP_TEST_AI_DB=str(Path(folder) / 'knowledge.sqlite3'),
            SUPPORT_API_KEY='', SUPPORT_RAG_RETRY_ENABLED='false', AI_OLLAMA_BASE_URL='http://127.0.0.1:1')
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
        product = SPU.objects.create(name='合成协议商品', catalog=category)
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
        conversation = SupportConversation.objects.create(user=buyer, revision=1)
        SupportTurn.objects.create(user=buyer, conversation=conversation, sequence=1, request_id=uuid.uuid4(),
            request_hash='synthetic', user_text='推荐绿茶', answer='合成历史', intent='recommendation', response={})
        count = 0
        def access(message='推荐绿茶', **extra):
            return AgentDataAccess(config=config(), message=message, owner_id=buyer.pk, **extra)

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
        connections.close_all()
        summary = {'status':'passed','checks':count,
                   'databases':('disposable MySQL' if arguments.mysql else 'disposable SQLite') + (' + PostgreSQL' if arguments.postgres else ' + SQLite knowledge'),
                   'transport':'real stdio MCP SDK -> persistent Django backend','provider_calls':0}
    print(json.dumps(dict(summary, cleanup='completed')))


if __name__ == '__main__':
    run()
