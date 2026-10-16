"""Application-configured model adapter; the Agent graph receives this adapter."""

import json

from django.conf import settings
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableLambda


class AgentModel(Runnable):
    """DeepSeek thinking rejects forced tool_choice; use schema-guided JSON there."""

    def __init__(self, client, thinking):
        self.client = client
        self.thinking = thinking

    def invoke(self, input, config=None, **kwargs):
        return self.client.invoke(input, config=config, **kwargs)

    def with_structured_output(self, schema):
        if self.thinking != 'enabled':
            return self.client.with_structured_output(schema)

        def add_schema(prompt):
            messages = prompt.to_messages() if hasattr(prompt, 'to_messages') else (
                [HumanMessage(content=prompt)] if isinstance(prompt, str) else list(prompt))
            instruction = 'Return a JSON object matching this JSON Schema exactly. Do not add Markdown.\n' + json.dumps(schema.model_json_schema(), ensure_ascii=False)
            return [SystemMessage(content=instruction)] + messages

        return RunnableLambda(add_schema) | self.client.with_structured_output(schema, method='json_mode')


def configured_model(config=None, *, timeout=None, max_retries=1, max_tokens=None):
    if not settings.SUPPORT_API_KEY:
        raise RuntimeError('SUPPORT_API_KEY 未配置')
    thinking = config.thinking if config else settings.SUPPORT_THINKING
    options = {
        'model': config.model if config else settings.SUPPORT_MODEL, 'api_key': settings.SUPPORT_API_KEY,
        'temperature': 0, 'timeout': timeout if timeout is not None else (60 if thinking == 'enabled' else 20),
        'max_retries': max_retries,
    }
    if settings.SUPPORT_BASE_URL:
        options['base_url'] = settings.SUPPORT_BASE_URL
    if max_tokens is not None:
        options['max_tokens'] = max_tokens
    if thinking:
        options['extra_body'] = {'thinking': {'type': thinking}}
    return AgentModel(ChatOpenAI(**options), thinking)
