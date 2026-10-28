"""Content-free error diagnostics suitable for logs and application responses."""
import re
from pydantic import ValidationError
from .contracts import IntentEvidenceError


def error_diagnostic(exc, stage):
    fields = []
    if isinstance(exc, ValidationError):
        labels = {'too_long': '数量超过允许上限', 'missing': '缺少必填字段',
                  'literal_error': '字段值不在允许范围', 'extra_forbidden': '包含不支持的字段',
                  'value_error': '字段未通过安全或格式校验'}
        for item in exc.errors(include_input=False)[:8]:
            parts = [str(p) for p in item['loc']]
            allowed = {'required', 'preferred', 'excluded', 'categories', 'brands', 'keywords', 'price_min',
                       'price_max', 'budget_min', 'budget_max', 'budget_mode', 'quantity_per_product', 'distinct_count',
                       'currency', 'price_basis', 'evidence', 'field', 'value', 'source',
                       'source_id', 'context_turn_id', 'quote', 'action', 'missing_fields'}
            field = '.'.join(p if p in allowed or re.fullmatch(r'\d{1,2}', p) else 'unknown' for p in parts)
            fields.append({'field': field, 'code': item['type'],
                           'message': labels.get(item['type'], '字段格式不符合要求')})
            limit = item.get('ctx', {}).get('max_length')
            if type(limit) is int:
                fields[-1]['limit'] = limit
    diagnostic = {'stage': stage, 'error_type': type(exc).__name__, 'fields': fields}
    if isinstance(exc, IntentEvidenceError):
        diagnostic['fields'] = [{'field': exc.field, 'code': exc.code, 'message': str(exc)}]
    safe_reasons = {'未知的意向证据字段', '当前输入证据不能指定外来 ID', '长期记忆只能提供当前用户的软偏好',
                    '意向条件无法对应输入证据', '意向条件缺少原文或记忆依据', '筛选条件互相冲突', 'Unverified saved preference'}
    if type(exc) is ValueError and str(exc) in safe_reasons:
        diagnostic['message'] = str(exc)
    return diagnostic
