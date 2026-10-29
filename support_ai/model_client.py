"""Application-configured model adapter; the Agent graph receives this adapter."""

import json

from django.conf import settings
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda
from .cost_control import (RequestBudget, current_budget, input_upper_bound,
                           SCHEMA_STAGES)
from .streaming import progress, cancellation_callback


class SupportChatOpenAI(ChatOpenAI):
    """DeepSeek accepts max_tokens, not LangChain's renamed completion parameter."""
    def _get_request_payload(self, *args, **kwargs):
        payload = super()._get_request_payload(*args, **kwargs)
        if 'max_completion_tokens' in payload:
            payload['max_tokens'] = payload.pop('max_completion_tokens')
        return payload


class AgentModel(Runnable):
    """DeepSeek thinking rejects forced tool_choice; use schema-guided JSON there."""

    def __init__(self, client, thinking):
        self.client = client
        self.thinking = thinking

    def invoke(self, input, config=None, **kwargs):
        return self._invoke_stage(input, config, None, **kwargs)

    def with_structured_output(self, schema):
        def invoke(prompt, config=None):
            return self._invoke_stage(prompt, config, schema)
        return RunnableLambda(invoke)

    def _invoke_stage(self, prompt, config, schema, **kwargs):
        if set(kwargs) & {'max_tokens', 'max_completion_tokens', 'extra_body', 'max_retries', 'model', 'stream'}:
            raise ValueError('Model cost options must use the server stage policy')
        stage = SCHEMA_STAGES.get(getattr(schema, '__name__', ''), 'extraction')
        budget = current_budget() or RequestBudget()
        thinking, cap = budget.stage_policy[stage]
        configured_cap = self.client.max_tokens
        if configured_cap is not None:
            cap = min(cap, configured_cap)
        reservation = budget.reserve(stage, input_upper_bound(prompt, schema), cap)
        usage = None
        try:
            progress({'planning':'planning','verification':'verification','compliance':'compliance',
                      'knowledge':'generation','rewrite':'retrieval'}.get(stage,'generation'))
            client = self.client.model_copy(update={
                'max_tokens': reservation[1], 'max_retries': 0,
                'extra_body': {**(self.client.extra_body or {}), 'thinking': {'type': thinking}},
            })
            if schema is None:
                reply = client.invoke(prompt, config=config, **kwargs)
                usage = reply.usage_metadata
                return reply
            if thinking == 'enabled':
                messages = prompt.to_messages() if hasattr(prompt, 'to_messages') else (
                    [HumanMessage(content=prompt)] if isinstance(prompt, str) else list(prompt))
                instruction = 'Return a JSON object matching this JSON Schema exactly. Do not add Markdown.\n' + json.dumps(schema.model_json_schema(), ensure_ascii=False)
                prompt = [SystemMessage(content=instruction)] + messages
            # include_raw accounts for malformed structured output as well.
            method = 'json_mode' if thinking == 'enabled' else 'function_calling'
            reply = client.with_structured_output(schema, method=method, include_raw=True).invoke(prompt, config=config)
            usage = getattr(reply.get('raw'), 'usage_metadata', None)
            if reply.get('parsing_error') is not None:
                raise reply['parsing_error']
            if reply.get('parsed') is None:
                raise ValueError('Missing structured model output')
            return reply['parsed']
        finally:
            budget.settle(reservation, usage)


def configured_model(config=None, *, timeout=None, max_retries=0, max_tokens=None):
    if not settings.SUPPORT_API_KEY:
        raise RuntimeError('SUPPORT_API_KEY 未配置')
    thinking = config.thinking if config else settings.SUPPORT_THINKING
    options = {
        'model': config.model if config else settings.SUPPORT_MODEL, 'api_key': settings.SUPPORT_API_KEY,
        'temperature': 0, 'timeout': timeout if timeout is not None else (60 if thinking == 'enabled' else 20),
        # Each budget admission represents exactly one provider request.
        'max_retries': 0,
        # Aggregate structured chunks before validation; raw drafts/tool-call
        # fragments are never forwarded to the customer SSE stream.
        'streaming': True, 'stream_usage': True,
    }
    if settings.SUPPORT_BASE_URL:
        options['base_url'] = settings.SUPPORT_BASE_URL
    if max_tokens is not None:
        options['max_tokens'] = max_tokens
    from .mcp_tracing import remote_callback
    callback = remote_callback()
    callbacks = [item for item in (callback, cancellation_callback()) if item is not None]
    if callbacks:
        options['callbacks'] = callbacks
    if thinking:
        options['extra_body'] = {'thinking': {'type': thinking}}
    return AgentModel(SupportChatOpenAI(**options), thinking)


def lazy_configured_model(config):
    """Deterministic tools do not require provider credentials or availability."""
    class LazyModel(Runnable):
        client = None

        def get(self):
            if self.client is None:
                self.client = configured_model(config)
            return self.client

        def invoke(self, input, config=None, **kwargs):
            return self.get().invoke(input, config=config, **kwargs)

        def with_structured_output(self, schema):
            return RunnableLambda(lambda prompt, config=None: self.get().with_structured_output(schema).invoke(prompt, config=config))

    return LazyModel()
