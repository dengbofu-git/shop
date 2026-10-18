"""Platform-only Agent configuration and privacy-filtered OTel read APIs."""

import json
import re
import math
from datetime import timedelta

from django.conf import settings
from django.db import DatabaseError, transaction
from django.db.models import Avg, Count
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from requests import RequestException

from users.decorators import platform_permission_required
from support_ai.configuration import (
    configuration_data, configuration_row, effective_configuration, provider_models, validate_changes,
)
from support_ai.models import AgentConfiguration, AgentConfigurationChange, AgentSpan


def reply(data, status=200):
    response = JsonResponse(data, status=status, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-store'
    return response


@require_http_methods(['GET', 'PUT'])
@platform_permission_required('system_config')
def agent_settings(request):
    if not request.user_profile.is_active:
        return reply({'error': '账号已停用'}, 403)
    if request.method == 'GET':
        row = configuration_row()
        changes = AgentConfigurationChange.objects.select_related('operator').order_by('-id')[:10]
        return reply({'settings': configuration_data(row), 'api_key_configured': bool(settings.SUPPORT_API_KEY),
                      'rerank_models': list(settings.AI_RERANK_MODELS),
                      'history': [{'id': item.pk, 'operator': item.operator.username if item.operator else '已删除账号',
                                   'before': item.before, 'after': item.after, 'created_at': item.created_at.isoformat()}
                                  for item in changes]})
    if len(request.body) > 4000:
        return reply({'error': '设置内容过长'}, 413)
    try:
        data = json.loads(request.body)
        current = configuration_row()
        changes = validate_changes(data, current)
        with transaction.atomic():
            AgentConfiguration.objects.get_or_create(pk=1)
            row = AgentConfiguration.objects.select_for_update().get(pk=1)
            if data['revision'] != row.revision:
                return reply({'error': '设置已被其他运营人员更新，请刷新后重试'}, 409)
            before = configuration_data(row)
            for key, value in changes.items():
                setattr(row, key, value)
            row.revision += 1
            row.save()
            after = configuration_data(row)
            AgentConfigurationChange.objects.create(operator=request.user_profile, before=before, after=after)
        from support_ai.telemetry import refresh_runtime
        refresh_runtime(effective_configuration(row))
        return reply({'settings': after})
    except (ValueError, TypeError, UnicodeError) as exc:
        return reply({'error': str(exc) if isinstance(exc, ValueError) else '设置格式无效'}, 400)
    except RequestException:
        return reply({'error': '无法验证 DeepSeek 模型列表，请检查模型服务连接后重试'}, 503)
    except DatabaseError:
        return reply({'error': 'Agent 设置保存失败，请稍后再试'}, 503)


@require_http_methods(['GET'])
@platform_permission_required('system_config')
def agent_models(request):
    if not request.user_profile.is_active:
        return reply({'error': '账号已停用'}, 403)
    try:
        return reply({'models': provider_models(), 'current': effective_configuration().model})
    except (ValueError, RequestException):
        return reply({'error': '暂时无法读取 DeepSeek 模型列表，请检查服务器 API Key 和网络连接',
                      'current': effective_configuration().model}, 503)


@require_http_methods(['GET'])
@platform_permission_required('system_config')
def agent_retrieval_status(request):
    if not request.user_profile.is_active:
        return reply({'error': '账号已停用'}, 403)
    from ai_storage.reranking import reranker_status
    return reply({'service': reranker_status(), 'models': list(settings.AI_RERANK_MODELS)})


def span_data(row):
    return {'trace_id': row.trace_id, 'span_id': row.span_id, 'parent_span_id': row.parent_span_id,
            'name': row.name, 'started_at': row.started_at.isoformat(), 'duration_ms': round(row.duration_ms, 2),
            'status': row.status, 'attributes': row.attributes}


@require_http_methods(['GET'])
@platform_permission_required('system_config')
def agent_monitoring(request):
    if not request.user_profile.is_active:
        return reply({'error': '账号已停用'}, 403)
    try:
        hours = int(request.GET.get('hours', '24'))
        page = int(request.GET.get('page', '1'))
        if hours not in (1, 24, 168) or not 1 <= page <= 10000:
            raise ValueError()
    except ValueError:
        return reply({'error': '时间范围或页码无效'}, 400)
    since = timezone.now() - timedelta(hours=hours)
    roots = AgentSpan.objects.filter(name='support.chat', started_at__gte=since)
    summary = roots.aggregate(total=Count('id'), average_ms=Avg('duration_ms'))
    errors = roots.filter(status='ERROR').count()
    # Aggregate JSON values in Python for compatibility with the supported MySQL/SQLite versions.
    totals = {'input_tokens': 0, 'output_tokens': 0, 'model_calls': 0, 'retrieval_hits': 0, 'blocked': 0}
    for attrs in roots.values_list('attributes', flat=True).iterator(chunk_size=1000):
        for dest, source in [('input_tokens', 'gen_ai.usage.input_tokens'), ('output_tokens', 'gen_ai.usage.output_tokens'),
                             ('model_calls', 'agent.llm.calls'), ('retrieval_hits', 'agent.retrieval.hits')]:
            totals[dest] += attrs.get(source, 0)
        totals['blocked'] += int(attrs.get('agent.compliance.blocked', False))
    per_model = {}
    for attrs in roots.values_list('attributes', flat=True).iterator(chunk_size=1000):
        model = attrs.get('gen_ai.request.model', 'unknown')
        per_model[model] = per_model.get(model, 0) + 1
    rows = roots.order_by('-started_at')[(page - 1) * 20:page * 20]
    reranks = AgentSpan.objects.filter(name='knowledge.rerank', started_at__gte=since)
    rerank_summary = reranks.aggregate(calls=Count('id'), average_ms=Avg('duration_ms'))
    durations = sorted(reranks.order_by('-started_at').values_list('duration_ms', flat=True)[:10000])
    fallback_count = sum(attrs.get('agent.rerank.fallbacks', 0) for attrs in roots.values_list('attributes', flat=True).iterator(chunk_size=1000))
    rerank_summary.update(errors=reranks.filter(status='ERROR').count(), fallbacks=fallback_count,
                          average_ms=round(rerank_summary['average_ms'] or 0, 2),
                          p95_ms=round(durations[max(0, math.ceil(len(durations) * .95) - 1)], 2) if durations else 0,
                          p95_sample_count=len(durations))
    rerank_summary['error_rate'] = round(100 * rerank_summary['errors'] / rerank_summary['calls'], 2) if rerank_summary['calls'] else 0
    rerank_summary['fallback_rate'] = round(100 * fallback_count / rerank_summary['calls'], 2) if rerank_summary['calls'] else 0
    from support_ai.telemetry import telemetry_status
    return reply({'hours': hours, 'page': page, 'total': summary['total'], 'export_status': telemetry_status(),
                  'summary': dict(totals, requests=summary['total'], errors=errors,
                                  success_rate=round(100 * (summary['total'] - errors) / summary['total'], 2)
                                  if summary['total'] else None, average_ms=round(summary['average_ms'] or 0, 2),
                                  retrieval_errors=AgentSpan.objects.filter(name='knowledge.retrieve', status='ERROR',
                                                                           started_at__gte=since).count()),
                  'per_model': per_model, 'traces': [span_data(row) for row in rows],
                  'reranking': rerank_summary,
                  'telemetry_enabled': effective_configuration().telemetry_enabled})


@require_http_methods(['GET'])
@platform_permission_required('system_config')
def agent_trace(request, trace_id):
    if not request.user_profile.is_active:
        return reply({'error': '账号已停用'}, 403)
    if not re.fullmatch(r'[0-9a-f]{32}', trace_id):
        return reply({'error': 'Trace ID 无效'}, 400)
    spans = list(AgentSpan.objects.filter(trace_id=trace_id).order_by('started_at', 'id')[:200])
    if not spans:
        return reply({'error': '监控记录不存在'}, 404)
    return reply({'trace_id': trace_id, 'spans': [span_data(row) for row in spans]})
