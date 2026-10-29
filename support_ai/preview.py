"""Local interactive Agent sessions; customer conversations are never committed."""
import json
import time
import uuid
from dataclasses import asdict, replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from django.conf import settings
from django.db import close_old_connections
from django.utils import timezone
from langchain_core.callbacks import BaseCallbackHandler

from .configuration import effective_configuration
from .context import HISTORY_HOURS, HISTORY_TURNS, context_from_turns
from .model_client import lazy_configured_model
from .pii import redact
from .mcp_client import AgentDataAccess
from .views import load_agent_preferences
from .query_rewrite import QueryPolicy
from .telemetry import observe_agent
from .tool_services import create_tool_handlers
from .workflow import build_graph, fixed_result
from .cost_control import CostPolicy, STAGES, stage_options
from .order_contracts import prepare_order_input
from .order_queries import OrderQueryContext

from tea_saas.versioning import module_version
PREVIEW_RUNTIME_VERSION = module_version('support_ai')


def safe_record(value):
    """Redact every string before local persistence, including nested diagnostics."""
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {key: safe_record(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [safe_record(item) for item in value]
    return value


class Usage(BaseCallbackHandler):
    def __init__(self):
        self.calls = self.input_tokens = self.output_tokens = 0

    def on_chat_model_start(self, serialized, messages, **kwargs):
        self.calls += 1

    def on_llm_end(self, response, **kwargs):
        usage = next((getattr(getattr(item, 'message', None), 'usage_metadata', None)
                      for group in response.generations for item in group
                      if getattr(getattr(item, 'message', None), 'usage_metadata', None)), None)
        if usage:
            self.input_tokens += usage.get('input_tokens', 0)
            self.output_tokens += usage.get('output_tokens', 0)
        else:
            usage = (response.llm_output or {}).get('token_usage', {})
            self.input_tokens += usage.get('prompt_tokens', 0)
            self.output_tokens += usage.get('completion_tokens', 0)


class PreviewSession:
    def __init__(self, user=None, log_dir=None, telemetry=False):
        self.user = user
        self.telemetry = telemetry
        self.log_dir = Path(log_dir or settings.BASE_DIR / 'reports' / 'agent-preview').resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        # Model configuration is validated when a request actually needs it.
        self.new()

    def configuration(self):
        config = effective_configuration()
        return config if self.telemetry else replace(config, telemetry_enabled=False, export_enabled=False)

    def status(self):
        config = self.configuration()
        return {'agent_version': PREVIEW_RUNTIME_VERSION, 'model': config.model, 'thinking': config.thinking, 'revision': config.revision,
                'rerank_enabled': config.rerank_enabled, 'rerank_model': config.rerank_model,
                'retrieval_candidates': config.retrieval_candidates, 'retrieval_top_k': config.retrieval_top_k,
                'scope': 'selected_buyer' if self.user else 'public', 'telemetry': config.telemetry_enabled,
                'rag_query_rewrite': asdict(QueryPolicy.current()),
                'model_cost_policy': {'limits': asdict(CostPolicy.current()), 'stages': {
                    stage: {'thinking': stage_options(stage)[0], 'max_tokens': stage_options(stage)[1]}
                    for stage in STAGES}},
                'history_turns': HISTORY_TURNS, 'log_file': str(self.log_path) if hasattr(self, 'log_path') else None}

    def _append(self, record):
        with self.log_path.open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(safe_record(record), ensure_ascii=False, default=str) + '\n')

    def new(self):
        self.session_id = uuid.uuid4().hex
        self.log_path = self.log_dir / (timezone.localtime().strftime('%Y%m%d-%H%M%S-') + self.session_id + '.jsonl')
        self.turns = []
        self.sequence = 0
        self.last_record = None
        self.last_error = None
        self.order_binding = SimpleNamespace(active_order_id='', active_order_at=None)
        self._append({'event': 'session_start', 'session_id': self.session_id,
                      'created_at': timezone.now().isoformat(), 'configuration': self.status()})

    def history(self):
        cutoff = timezone.now() - timedelta(hours=HISTORY_HOURS)
        return context_from_turns(turn for turn in reversed(self.turns) if turn.created_at >= cutoff)

    def ask(self, message):
        if not isinstance(message, str) or not message.strip() or len(message) > 1000:
            raise ValueError('请输入 1 至 1000 字的问题。')
        close_old_connections()
        started = time.perf_counter()
        safe_message, references = prepare_order_input(message)
        history = self.history()
        order_query_context = OrderQueryContext(owner_id=self.user.pk if self.user else None,
            references=references, active_order_id=self.order_binding.active_order_id,
            active_order_at=self.order_binding.active_order_at,
            previous_page=next((turn.response['order_result'] for turn in reversed(self.turns)
                if turn.created_at >= timezone.now() - timedelta(hours=HISTORY_HOURS)
                and turn.response.get('order_result')), {}))
        usage = Usage()
        result = None
        retriever = None
        self.last_error = None
        try:
            config = self.configuration()
            result = fixed_result(safe_message, history)
            if result is None:
                with observe_agent(config) as observation:
                    memory = None
                    retriever = AgentDataAccess(config=config, message=safe_message,
                        owner_id=self.user.pk if self.user else None, references=references,
                        order_context=order_query_context, preview_history=history)
                    if self.user:
                        memory = load_agent_preferences(retriever, safe_message, history)
                    model = lazy_configured_model(config)

                    def tool_factory(state):
                        handlers = create_tool_handlers(
                            model, retriever.search,
                            state['safe_message'], state['resolved_question'], state.get('recent_turns', []), memory,
                            knowledge_context_chars=config.retrieval_context_chars,
                            scoped_knowledge_search=retriever.scoped_search, knowledge_notes=retriever.notes,
                            order_query_context=order_query_context, data_access=retriever)
                        return handlers

                    graph = build_graph(model, tool_factory=tool_factory)
                    callbacks = [usage] + ([observation.callback] if observation.callback else [])
                    result = graph.invoke({'message': safe_message, 'recent_turns': history, 'memory': memory,
                                           'owner_id': self.user.pk if self.user else None},
                                          config={'callbacks': callbacks})
                    observation.finish(result)
                    if result['tool_results'] and all(r['status'] in ('error', 'skipped') for r in result['tool_results']):
                        raise RuntimeError('All Agent tools failed')
                    response = dict(result['response'], pii_redacted=safe_message != message.strip())
                    if observation.trace_id:
                        response['trace_id'] = observation.trace_id
            else:
                response = dict(result['response'], pii_redacted=safe_message != message.strip())
            self.sequence += 1
            record = safe_record({'event': 'turn', 'session_id': self.session_id, 'sequence': self.sequence,
                                  'created_at': timezone.now().isoformat(), 'message': safe_message,
                                  'resolved_question': result['resolved_question'], 'context_turns': len(history),
                                  'model': config.model, 'thinking': config.thinking, 'config_revision': config.revision,
                                  'compliance_blocked': result.get('compliance_blocked', False),
                                  'elapsed_seconds': round(time.perf_counter() - started, 3),
                                  'model_calls': usage.calls + (retriever.remote_usage['calls'] if retriever else 0),
                                  'input_tokens': usage.input_tokens + (retriever.remote_usage['input_tokens'] if retriever else 0),
                                  'output_tokens': usage.output_tokens + (retriever.remote_usage['output_tokens'] if retriever else 0), 'response': response,
                                  'retrieval': retriever.audit if retriever else []})
            # Persist before advancing session memory. Never call commit_turn().
            self._append(record)
            self.turns.append(SimpleNamespace(pk='preview-' + str(self.sequence), user_text=safe_message,
                                             answer=response['answer'], intent=response['intent'],
                                             response=response, created_at=timezone.now()))
            self.turns = self.turns[-HISTORY_TURNS:]
            if order_query_context.binding_changed and self.user:
                selected_order = order_query_context.selected_order_id
                self.order_binding = SimpleNamespace(active_order_id=selected_order,
                                                     active_order_at=timezone.now() if selected_order else None)
            self.last_record = record
            return record
        except Exception as exc:
            self.last_error = safe_record({
                'event': 'error', 'created_at': timezone.now().isoformat(), 'message': safe_message,
                'error_type': type(exc).__name__, 'elapsed_seconds': round(time.perf_counter() - started, 3),
                'context_turns': len(history), 'model_calls': usage.calls,
                'input_tokens': usage.input_tokens, 'output_tokens': usage.output_tokens,
                'retrieval': retriever.audit if retriever else [],
                'resolved_question': result.get('resolved_question') if result else None,
                'task_plan': result.get('plan') if result else None,
                'tasks': [{'id': r['step_id'], 'tool': r['tool'], 'status': r['status'],
                           'error_type': r['data'].get('error_type'),
                           'condition_source': r['data'].get('condition_source'),
                           'extraction_attempts': r['data'].get('extraction_attempts'),
                           'diagnostics': r['data'].get('diagnostics', [])} for r in result.get('tool_results', [])] if result else [],
            })
            self._append(self.last_error)
            raise
        finally:
            if retriever is not None:
                retriever.close()
            close_old_connections()
