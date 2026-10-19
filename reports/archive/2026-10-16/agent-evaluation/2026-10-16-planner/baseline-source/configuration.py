"""Versioned, request-scoped Agent configuration and authenticated provider catalog."""

from dataclasses import dataclass
import math
from urllib.parse import urlsplit

import requests
from django.conf import settings

from .models import AgentConfiguration


@dataclass(frozen=True)
class AgentConfig:
    model: str
    thinking: str
    telemetry_enabled: bool
    export_enabled: bool
    otlp_endpoint: str
    revision: int
    rerank_enabled: bool = False
    rerank_model: str = 'BAAI/bge-reranker-v2-m3'
    retrieval_candidates: int = 30
    retrieval_top_k: int = 5
    retrieval_per_document: int = 2
    retrieval_context_chars: int = 12000
    rerank_timeout_ms: int = 5000
    rerank_min_score: float = None
    rerank_fallback: bool = True


RETRIEVAL_FIELDS = ('rerank_enabled', 'rerank_model', 'retrieval_candidates', 'retrieval_top_k',
                    'retrieval_per_document', 'retrieval_context_chars', 'rerank_timeout_ms',
                    'rerank_min_score', 'rerank_fallback')


def configuration_row():
    return AgentConfiguration.objects.filter(pk=1).first() or AgentConfiguration()


def effective_configuration(row=None):
    row = row if row is not None else configuration_row()
    return AgentConfig(
        model=row.model or settings.SUPPORT_MODEL,
        thinking=settings.SUPPORT_THINKING if row.thinking == 'inherit' else row.thinking,
        telemetry_enabled=row.telemetry_enabled,
        export_enabled=row.export_enabled,
        otlp_endpoint=row.otlp_endpoint.rstrip('/'),
        revision=row.revision,
        **{key: getattr(row, key) for key in RETRIEVAL_FIELDS},
    )


def configuration_data(row):
    effective = effective_configuration(row)
    return {
        'model': effective.model, 'thinking': row.thinking,
        'effective_thinking': effective.thinking,
        'telemetry_enabled': row.telemetry_enabled, 'export_enabled': row.export_enabled,
        'otlp_endpoint': effective.otlp_endpoint, 'revision': row.revision,
        **{key: getattr(effective, key) for key in RETRIEVAL_FIELDS},
    }


def provider_models():
    if not settings.SUPPORT_API_KEY:
        raise ValueError('服务器尚未配置 DeepSeek API Key')
    response = requests.get(
        settings.SUPPORT_BASE_URL.rstrip('/') + '/models',
        headers={'Authorization': 'Bearer ' + settings.SUPPORT_API_KEY}, timeout=(3, 8),
    )
    response.raise_for_status()
    data = response.json().get('data', [])
    models = sorted({item['id'] for item in data if isinstance(item, dict)
                     and isinstance(item.get('id'), str) and item['id'].startswith('deepseek-')
                     and len(item['id']) <= 100})
    if not models:
        raise ValueError('模型服务未返回可用的 DeepSeek 模型')
    return models


def validate_changes(data, current):
    fields = {'model', 'thinking', 'telemetry_enabled', 'export_enabled', 'otlp_endpoint', 'revision'}
    if not isinstance(data, dict) or not fields <= set(data) or set(data) - fields - set(RETRIEVAL_FIELDS):
        raise ValueError('请提交完整的 Agent 设置，且不要包含未知字段')
    if type(data['revision']) is not int or data['revision'] < 0:
        raise ValueError('配置版本无效')
    model = data['model']
    if not isinstance(model, str) or not model.startswith('deepseek-') or len(model) > 100:
        raise ValueError('请选择有效的 DeepSeek 模型')
    if model != effective_configuration(current).model and model not in provider_models():
        raise ValueError('该模型不在当前 DeepSeek 服务提供的模型列表中')
    if data['thinking'] not in ('inherit', 'enabled', 'disabled'):
        raise ValueError('思考模式无效')
    if any(type(data[key]) is not bool for key in ('telemetry_enabled', 'export_enabled')):
        raise ValueError('监控开关必须为布尔值')
    endpoint = data['otlp_endpoint']
    if not isinstance(endpoint, str) or len(endpoint) > 200 or any(char.isspace() for char in endpoint):
        raise ValueError('OTLP 地址无效')
    parsed = urlsplit(endpoint)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError('OTLP 端口无效')
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ('', '/')
            or (port is not None and not 1 <= port <= 65535)):
        raise ValueError('请填写 OTLP HTTP 基地址，例如 http://127.0.0.1:4318，不含路径或凭据')
    if data['export_enabled'] and not data['telemetry_enabled']:
        raise ValueError('请先开启 Agent 监控再启用 OTLP 导出')
    retrieval = {key: data.get(key, getattr(current, key)) for key in RETRIEVAL_FIELDS}
    if any(type(retrieval[key]) is not bool for key in ('rerank_enabled', 'rerank_fallback')):
        raise ValueError('重排序开关和降级策略必须为布尔值')
    if retrieval['rerank_model'] not in settings.AI_RERANK_MODELS:
        raise ValueError('请选择服务器已部署的重排序模型')
    for key, low, high in [('retrieval_candidates', 1, 100), ('retrieval_top_k', 1, 20),
                           ('retrieval_per_document', 1, 20), ('retrieval_context_chars', 1000, 30000),
                           ('rerank_timeout_ms', 500, 30000)]:
        if type(retrieval[key]) is not int or not low <= retrieval[key] <= high:
            raise ValueError('检索数量、上下文长度或超时时间超出允许范围')
    if not retrieval['retrieval_per_document'] <= retrieval['retrieval_top_k'] <= retrieval['retrieval_candidates']:
        raise ValueError('每来源上限不能大于最终条数，最终条数不能大于召回条数')
    score = retrieval['rerank_min_score']
    if score is not None and (type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1):
        raise ValueError('相关性阈值须留空或填写 0–1 之间的数值')
    return dict({key: data[key] for key in fields - {'revision'}}, **retrieval)
