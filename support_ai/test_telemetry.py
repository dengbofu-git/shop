import json
import uuid
from dataclasses import replace
from unittest.mock import patch

from django.test import TestCase
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, LLMResult
from langchain_core.runnables import RunnableLambda

from tea_saas.utils import jwt_encode
from users.models import Permission, Role, RolePermission, UserProfile, UserRole
from .configuration import AgentConfig, effective_configuration
from .models import AgentConfiguration, AgentConfigurationChange, AgentSpan
from .model_client import configured_model
from .telemetry import agent_span, observe_agent, refresh_runtime, retrieval_hits, shutdown_telemetry


def default_config(**kwargs):
    return replace(AgentConfig('deepseek-flash', 'disabled', True, False, 'http://127.0.0.1:4318', 0), **kwargs)


class AgentTelemetryTests(TestCase):
    def tearDown(self):
        shutdown_telemetry()

    def test_span_parentage_token_usage_and_privacy(self):
        secret = 'buyer@example.com private conversation'
        with observe_agent(default_config()) as observation:
            with agent_span('agent.question_answering') as node:
                node.set_attribute('user.prompt', secret)  # Local projection must reject unexpected attributes.
                run_id = uuid.uuid4()
                observation.callback.on_chat_model_start({}, [[secret]], run_id=run_id)
                observation.callback.on_llm_end(LLMResult(generations=[[ChatGeneration(message=AIMessage(
                    content=secret, usage_metadata={'input_tokens': 10, 'output_tokens': 4, 'total_tokens': 14},
                ))]]), run_id=run_id)
                retrieval_hits(5)
            observation.finish({'intent': 'question_answering'})
            trace_id = observation.trace_id
        root = AgentSpan.objects.get(name='support.chat')
        node = AgentSpan.objects.get(name='agent.question_answering')
        llm = AgentSpan.objects.get(name='chat.deepseek')
        self.assertEqual(root.trace_id, trace_id)
        self.assertEqual(llm.parent_span_id, node.span_id)
        self.assertEqual(node.parent_span_id, root.span_id)
        self.assertEqual(root.attributes['gen_ai.usage.input_tokens'], 10)
        self.assertEqual(root.attributes['gen_ai.usage.output_tokens'], 4)
        self.assertEqual(root.attributes['agent.llm.calls'], 1)
        self.assertEqual(root.attributes['agent.retrieval.hits'], 5)
        self.assertNotIn(secret, json.dumps(list(AgentSpan.objects.values('attributes'))))

    def test_errors_record_class_without_exception_message(self):
        with self.assertRaises(TimeoutError):
            with observe_agent(default_config()):
                with agent_span('knowledge.retrieve'):
                    raise TimeoutError('sensitive raw payload')
        for row in AgentSpan.objects.all():
            self.assertEqual(row.status, 'ERROR')
            self.assertEqual(row.attributes['error.type'], 'TimeoutError')
            self.assertNotIn('sensitive', json.dumps(row.attributes))

    def test_disabled_monitoring_creates_no_records(self):
        with observe_agent(default_config(telemetry_enabled=False)) as observation:
            self.assertIsNone(observation.callback)
            self.assertEqual(observation.trace_id, '')
            with agent_span('agent.classify'):
                pass
        self.assertFalse(AgentSpan.objects.exists())

    def test_model_error_closes_child_span_and_counts_call_without_logging_payload(self):
        error = RuntimeError('secret provider payload')
        with self.assertRaises(RuntimeError):
            with observe_agent(default_config()) as observation:
                run_id = uuid.uuid4()
                observation.callback.on_chat_model_start({}, [], run_id=run_id)
                observation.callback.on_llm_error(error, run_id=run_id)
                raise error
        root = AgentSpan.objects.get(name='support.chat')
        model = AgentSpan.objects.get(name='chat.deepseek')
        self.assertEqual(root.attributes['agent.llm.calls'], 1)
        self.assertEqual(model.status, 'ERROR')
        self.assertEqual(model.parent_span_id, root.span_id)
        self.assertNotIn('secret', json.dumps(model.attributes))

    def test_configuration_refresh_keeps_inflight_trace_alive(self):
        with observe_agent(default_config()) as observation:
            old = observation.runtime
            refresh_runtime(default_config(telemetry_enabled=False))
            self.assertTrue(old.retired)
            self.assertFalse(old.closed)
            with agent_span('agent.compliance'):
                pass
        self.assertTrue(old.closed)
        self.assertEqual(AgentSpan.objects.count(), 2)

    def test_persistence_failure_does_not_break_agent(self):
        with patch.object(AgentSpan.objects, 'bulk_create', side_effect=RuntimeError('sensitive')):
            with observe_agent(default_config()) as observation:
                observation.finish({'intent': 'question_answering'})

    def test_thinking_mode_structured_output_contains_schema_without_forced_tool_choice(self):
        from .workflow import IntentScores
        captured = []

        def parse(messages):
            captured.extend(messages)
            return IntentScores(recommendation=.1, question_answering=.9, after_sales=.1)

        with patch('support_ai.model_client.ChatOpenAI') as chat:
            chat.return_value.with_structured_output.return_value = RunnableLambda(parse)
            model = configured_model(default_config(thinking='enabled'))
            result = model.with_structured_output(IntentScores).invoke('Introduce green tea')
        chat.return_value.with_structured_output.assert_called_once_with(IntentScores, method='json_mode')
        self.assertEqual(result.question_answering, .9)
        self.assertIn('"question_answering"', captured[0].content)
        self.assertEqual(captured[1].content, 'Introduce green tea')


class AgentOperationsTests(TestCase):
    def setUp(self):
        self.operator = UserProfile.objects.create(username='operator', password='unused', email='operator@test.com', phone='', is_active=True)
        self.buyer = UserProfile.objects.create(username='buyer', password='unused', email='buyer@test.com', phone='', is_active=True)
        role = Role.objects.create(code='admin', name='Operator')
        permission = Permission.objects.create(code='system_config', name='System configuration')
        RolePermission.objects.create(role=role, permission=permission)
        UserRole.objects.create(role=role, user_profile=self.operator)
        self.auth = {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': self.operator.pk})}
        self.buyer_auth = {'HTTP_AUTHORIZATION': 'Bearer ' + jwt_encode({'id': self.buyer.pk})}
        self.payload = {'model': 'deepseek-v4-pro', 'thinking': 'disabled', 'telemetry_enabled': True,
                        'export_enabled': False, 'otlp_endpoint': 'http://127.0.0.1:4318', 'revision': 0}

    def tearDown(self):
        shutdown_telemetry()

    def put(self, payload=None, auth=None):
        with patch('support_ai.configuration.provider_models', return_value=['deepseek-flash', 'deepseek-v4-pro']):
            return self.client.put('/v1/admin-panel/agent/settings', data=json.dumps(payload or self.payload),
                                   content_type='application/json', **(auth or self.auth))

    def test_buyer_and_anonymous_cannot_read_or_modify_configuration(self):
        for suffix in ('settings', 'monitoring', 'models', 'traces/' + 'a' * 32):
            self.assertEqual(self.client.get('/v1/admin-panel/agent/' + suffix, **self.buyer_auth).status_code, 403)
            self.assertEqual(self.client.get('/v1/admin-panel/agent/' + suffix).status_code, 401)
        self.assertEqual(self.put(auth=self.buyer_auth).status_code, 403)
        self.assertFalse(AgentConfiguration.objects.exists())

    def test_inactive_operator_is_forbidden(self):
        self.operator.is_active = False
        self.operator.save()
        self.assertEqual(self.put().status_code, 403)

    def test_switch_changes_next_model_and_has_versioned_audit(self):
        self.assertEqual(self.put().status_code, 200)
        config = effective_configuration()
        self.assertEqual(config.model, 'deepseek-v4-pro')
        with patch('support_ai.model_client.ChatOpenAI') as chat:
            configured_model(config)
        self.assertEqual(chat.call_args.kwargs['model'], 'deepseek-v4-pro')
        self.assertEqual(AgentConfigurationChange.objects.count(), 1)
        self.assertEqual(AgentConfigurationChange.objects.get().operator_id, self.operator.pk)
        self.assertEqual(self.put().status_code, 409)
        self.assertEqual(AgentConfigurationChange.objects.count(), 1)
        body = self.client.get('/v1/admin-panel/agent/settings', **self.auth).json()
        self.assertNotIn('SUPPORT_API_KEY', json.dumps(body))
        self.assertEqual(body['settings']['revision'], 1)

    def test_invalid_model_and_collector_address_are_rejected(self):
        for field, value in [('model', 'deepseek-nonexistent'), ('model', 'other-provider'),
                             ('otlp_endpoint', 'file:///tmp/export'), ('otlp_endpoint', 'http://u:p@localhost:4318'),
                             ('otlp_endpoint', 'http://localhost:4318/v1/traces'), ('telemetry_enabled', 'true'),
                             ('revision', True), ('thinking', 'unknown')]:
            with self.subTest(field=field, value=value):
                self.assertEqual(self.put(dict(self.payload, **{field: value})).status_code, 400)
        self.assertFalse(AgentConfigurationChange.objects.exists())

    def test_catalog_is_loaded_from_authenticated_provider(self):
        with patch('admin_panel.agent_views.provider_models', return_value=['deepseek-flash', 'deepseek-v4-pro']):
            response = self.client.get('/v1/admin-panel/agent/models', **self.auth)
        self.assertEqual(response.json()['models'], ['deepseek-flash', 'deepseek-v4-pro'])

    def test_monitoring_summary_and_trace_detail_come_from_otel_spans(self):
        with observe_agent(default_config()) as observation:
            with agent_span('agent.classify'):
                pass
            observation.finish({'intent': 'question_answering'})
        response = self.client.get('/v1/admin-panel/agent/monitoring', **self.auth)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['summary']['requests'], 1)
        self.assertEqual(response.json()['summary']['success_rate'], 100)
        detail = self.client.get('/v1/admin-panel/agent/traces/' + observation.trace_id, **self.auth)
        self.assertEqual(len(detail.json()['spans']), 2)
        self.assertEqual(self.client.get('/v1/admin-panel/agent/monitoring?hours=999', **self.auth).status_code, 400)

    def test_platform_page_contains_settings_and_monitoring(self):
        html = self.client.get('/admin_agents.html').content.decode()
        for expected in ('agent-settings', 'trace-rows', 'otlp-endpoint', 'agent-model'):
            self.assertIn(expected, html)
