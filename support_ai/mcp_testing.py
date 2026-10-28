"""Explicit synthetic MCP transport fixtures. Never imported by application code."""
import json
import weakref
from types import SimpleNamespace

from unittest.mock import patch

from .configuration import AgentConfig
from .mcp_backend import DataSession
from .mcp_client import AgentDataAccess


def config():
    return AgentConfig(model='synthetic', thinking='disabled', telemetry_enabled=False,
                       export_enabled=False, otlp_endpoint='', revision=1)


class SyntheticMcpTransport:
    def __init__(self, environment):
        self.session = DataSession(environment['TEA_SAAS_AGENT_GRANT'])
        self.tools = set(self.session.grant['allowed_tools'])
        self.closed = False
        self.calls = []

    def request(self, method, params, timeout=None):
        assert method == 'tools/call' and not self.closed
        self.calls.append(json.loads(json.dumps(params)))
        payload = self.session.invoke(params['name'], params['arguments'])
        return {'structuredContent':payload, 'isError':payload['status'] == 'error'}

    def close(self):
        self.closed = True


def enable_synthetic_mcp(test):
    transport = patch('support_ai.mcp_client.StdioMcpTransport', SyntheticMcpTransport)
    transport.start()
    test.addCleanup(transport.stop)


def create_tool_handlers(model, knowledge_search, message, resolved_question, history, memory,
                         *args, **kwargs):
    """Unit fixtures explicitly inject protocol results, not a production fallback."""
    from .tool_services import create_tool_handlers as production
    order_context = kwargs.get('order_query_context')
    access = AgentDataAccess(config=config(), message=message, preview_history=history,
        owner_id=order_context.owner_id if order_context else None,
        references=order_context.references if order_context else None, order_context=order_context)
    access.transport = SyntheticMcpTransport(access.environment)
    weakref.finalize(access, access.folder.cleanup)
    access.transport.session.memory = memory
    access.transport.session.memory_loaded = True
    if knowledge_search:
        scoped = kwargs.get('scoped_knowledge_search')
        access.transport.session.retriever = SimpleNamespace(
            search=knowledge_search,
            scoped_search=scoped or (lambda query, category, scope: knowledge_search(query)),
            notes=kwargs.get('knowledge_notes') or (lambda: []), audit=[])
    handlers = production(model, None, message, resolved_question, history, memory,
                          *args, **kwargs, data_access=access)
    # Callers retain this fixture only for an invoke. Explicit cleanup is also
    # available to standalone tests that keep the handlers for longer.
    return handlers


def build_graph(model, knowledge_search=None, tool_factory=None):
    from .workflow import build_graph as production
    if knowledge_search is not None and tool_factory is None:
        def tool_factory(state):
            return create_tool_handlers(model, lambda query:knowledge_search(query, state.get('owner_id')),
                state['safe_message'], state['resolved_question'], state.get('recent_turns', []), state.get('memory'))
    return production(model, tool_factory=tool_factory)
