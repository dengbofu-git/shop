"""Application-configured model adapter; the Agent graph receives this adapter."""

from django.conf import settings
from langchain_openai import ChatOpenAI


def configured_model():
    if not settings.SUPPORT_API_KEY:
        raise RuntimeError('SUPPORT_API_KEY 未配置')
    options = {
        'model': settings.SUPPORT_MODEL, 'api_key': settings.SUPPORT_API_KEY,
        'temperature': 0, 'timeout': 20, 'max_retries': 1,
    }
    if settings.SUPPORT_BASE_URL:
        options['base_url'] = settings.SUPPORT_BASE_URL
    if settings.SUPPORT_THINKING:
        options['extra_body'] = {'thinking': {'type': settings.SUPPORT_THINKING}}
    return ChatOpenAI(**options)
