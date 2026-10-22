"""Pure Agent contracts. No Django models, database handles or query expressions."""

import re
from decimal import Decimal, InvalidOperation
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .pii import contains_pii
from tea_saas.currency import RATES


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Preferences(Contract):
    categories: List[str] = Field(default_factory=list, max_length=5)
    brands: List[str] = Field(default_factory=list, max_length=5)
    keywords: List[str] = Field(default_factory=list, max_length=5)

    @field_validator('categories', 'brands', 'keywords')
    @classmethod
    def safe_terms(cls, values):
        result = []
        for value in values:
            value = value.strip()
            if not value or len(value) > 40 or contains_pii(value) or any(ord(c) < 32 for c in value):
                raise ValueError('偏好或查询词必须为 1 至 40 字且不含个人信息')
            if value not in result:
                result.append(value)
        return result


class QueryConditions(Contract):
    """Request filters have their own bounds, independent of saved preferences."""
    categories: List[str] = Field(default_factory=list, max_length=12)
    brands: List[str] = Field(default_factory=list, max_length=10)
    keywords: List[str] = Field(default_factory=list, max_length=10)

    @field_validator('categories', 'brands', 'keywords')
    @classmethod
    def safe_terms(cls, values):
        return Preferences.safe_terms(values)


class RecommendationOptions(Contract):
    mode: Literal['flat', 'by_category'] = 'flat'
    category_scope: Literal['requested', 'basic_tea_types'] = 'requested'
    per_category_limit: int = Field(default=1, ge=1, le=4)
    total_limit: int = Field(default=12, ge=1, le=12)
    include_reasons: bool = True
    clarification: str = ''


class RequiredConditions(QueryConditions):
    price_min: Optional[str] = None
    price_max: Optional[str] = None
    budget_min: Optional[str] = None
    budget_max: Optional[str] = None
    quantity_per_product: Optional[int] = Field(default=None, ge=1, le=100)
    distinct_count: Optional[int] = Field(default=None, ge=1, le=4)
    currency: Optional[Literal['USD', 'AED', 'SAR', 'CNY', 'EUR']] = None
    price_basis: Optional[Literal['unit', 'total', 'unknown']] = None

    @field_validator('price_min', 'price_max', 'budget_min', 'budget_max')
    @classmethod
    def money(cls, value):
        if value is not None:
            if not re.fullmatch(r'(?:0|[1-9]\d{0,7})(?:\.\d{1,2})?', value):
                raise ValueError('金额必须为非负十进制字符串，最多两位小数')
            return format(Decimal(value), '.2f')
        return value

    @model_validator(mode='after')
    def valid_range(self):
        if self.price_min is not None and self.price_max is not None:
            if Decimal(self.price_min) > Decimal(self.price_max):
                raise ValueError('最低价不能大于最高价')
        if self.budget_min is not None and self.budget_max is not None:
            if Decimal(self.budget_min) > Decimal(self.budget_max):
                raise ValueError('最低总预算不能大于最高总预算')
        return self


EvidenceField = Literal[
    'required.categories', 'required.brands', 'required.keywords',
    'required.price_min', 'required.price_max', 'required.currency', 'required.price_basis',
    'required.budget_min', 'required.budget_max', 'required.quantity_per_product', 'required.distinct_count',
    'preferred.categories', 'preferred.brands', 'preferred.keywords',
    'excluded.categories', 'excluded.brands', 'excluded.keywords',
]


class IntentEvidence(Contract):
    field: EvidenceField = Field(description='Exact section.field path; arrays use the field itself, without [index]. '
        'Purchase filters and explicit bundle quantity/count need evidence. Never use limit, action, reasons or missing_fields here.')
    value: str = Field(min_length=1, max_length=40)
    source: Literal['CURRENT', 'CONTEXT', 'MEMORY']
    source_id: Optional[str] = Field(default=None, max_length=80)
    quote: str = Field(min_length=1, max_length=300)


class RecommendationIntent(Contract):
    action: Literal['SEARCH', 'CLARIFY']
    required: RequiredConditions = Field(default_factory=RequiredConditions)
    preferred: QueryConditions = Field(default_factory=QueryConditions)
    excluded: QueryConditions = Field(default_factory=QueryConditions)
    evidence: List[IntentEvidence] = Field(default_factory=list, max_length=40)
    missing_fields: List[Literal[
        'category', 'currency', 'budget_scope', 'budget_amount', 'bundle_constraints',
        'product_reference', 'unsupported_attribute', 'details'
    ]] = Field(default_factory=list, max_length=6)


def _value_supported(field, value, quote):
    if field.endswith(('price_min', 'price_max', 'budget_min', 'budget_max')):
        amounts = re.findall(r'(?<![\d.])\d+(?:\.\d{1,2})?(?![\d.])', quote)
        try:
            return any(Decimal(amount) == Decimal(value) for amount in amounts)
        except InvalidOperation:
            return False
    if field.endswith('currency'):
        aliases = {'USD': ('usd', '美元', '美金', '$'), 'AED': ('aed', '迪拉姆'),
                   'SAR': ('sar', '里亚尔'), 'CNY': ('cny', 'rmb', '人民币', '¥', '￥'), 'EUR': ('eur', '欧元', '€')}
        if value == 'CNY' and re.search(r'(?<![美欧日])元', quote):
            return True
        return any(alias in quote.lower() for alias in aliases[value])
    if field.endswith('price_basis'):
        if value == 'unit':
            return bool(re.search(r'每|单价|一盒|一包|一份|一罐|per\b|each\b|unit\b', quote, re.I))
        if value == 'total':
            return bool(re.search(r'总价|总预算|整笔|总共|合计|一共|\btotal\b|\boverall\b', quote, re.I))
        return True
    if field.endswith(('quantity_per_product', 'distinct_count')):
        numbers = re.findall(r'(?<!\d)\d+(?!\d)|[一二两三四五六七八九十]', quote)
        chinese = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
                   '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        return any(str(chinese.get(n, n)) == value for n in numbers)
    return value.casefold() in quote.casefold()


def canonicalize_total_budget(intent):
    """Read legacy total-price slots without ever applying them as SKU prices."""
    intent = RecommendationIntent.model_validate(intent).model_copy(deep=True)
    if intent.required.price_basis == 'total':
        for old, new in (('price_min', 'budget_min'), ('price_max', 'budget_max')):
            value = getattr(intent.required, old)
            if value is not None:
                existing = getattr(intent.required, new)
                if existing is not None and existing != value:
                    raise ValueError('总预算字段冲突')
                setattr(intent.required, new, value)
                setattr(intent.required, old, None)
                for item in intent.evidence:
                    if item.field == 'required.' + old:
                        item.field = 'required.' + new
    return RecommendationIntent.model_validate(intent.model_dump())


def validate_recommendation_intent(intent, message, recent_turns, memory):
    """Validate provenance before any query. Memory can only supply soft preferences."""
    intent = canonicalize_total_budget(intent)
    turns = {turn['turn_id']: turn['user_text'] for turn in recent_turns}
    evidence = {}
    for item in intent.evidence:
        parts = item.field.split('.')
        if len(parts) != 2 or parts[0] not in ('required', 'preferred', 'excluded'):
            raise ValueError('未知的意向证据字段')
        section = getattr(intent, parts[0])
        if parts[1] not in type(section).model_fields:
            raise ValueError('未知的意向证据字段')
        if item.source == 'CURRENT':
            if item.source_id is not None:
                raise ValueError('当前输入证据不能指定外来 ID')
            text = message
        elif item.source == 'CONTEXT':
            text = turns.get(item.source_id)
        else:
            if parts[0] != 'preferred' or not memory or item.source_id != memory['id']:
                raise ValueError('长期记忆只能提供当前用户的软偏好')
            values = memory['preferences'].get(parts[1], [])
            # The authenticated server record owns the text. Both semantic
            # planning and standalone tools use this same provenance boundary.
            if item.value in values:
                item.quote = item.value
            text = item.quote if item.quote in values and item.value in values else None
        if text is None or item.quote not in text or not _value_supported(item.field, item.value, item.quote):
            raise ValueError('意向条件无法对应输入证据')
        evidence.setdefault(item.field, []).append(item)

    for name in ('required', 'preferred', 'excluded'):
        section = getattr(intent, name)
        for field, value in section.model_dump().items():
            values = value if isinstance(value, list) else ([] if value is None else [value])
            for term in values:
                if not any((Decimal(item.value) == Decimal(term) if field in ('price_min', 'price_max', 'budget_min', 'budget_max')
                            else item.value == str(term)) for item in evidence.get(name + '.' + field, [])):
                    raise ValueError('意向条件缺少原文或记忆依据')
    for field in ('categories', 'brands', 'keywords'):
        required = getattr(intent.required, field)
        excluded = getattr(intent.excluded, field)
        if {v.casefold() for v in required} & {v.casefold() for v in excluded}:
            raise ValueError('筛选条件互相冲突')
        # A confirmed current/session constraint overrides a persistent soft preference.
        if required:
            setattr(intent.preferred, field, [])
        else:
            setattr(intent.preferred, field, [v for v in getattr(intent.preferred, field)
                                           if v.casefold() not in {x.casefold() for x in excluded}])
    previous_gaps = set(intent.missing_fields)
    intent.missing_fields = [f for f in intent.missing_fields if f not in ('currency', 'budget_scope', 'budget_amount')]
    hard = intent.required
    if hard.budget_min is not None or hard.budget_max is not None:
        if hard.price_basis != 'total':
            raise ValueError('总预算必须明确预算类型')
    if hard.price_basis == 'total':
        if hard.budget_max is None or Decimal(hard.budget_max) <= 0:
            intent.missing_fields.append('budget_amount')
        if hard.currency is not None and hard.currency not in RATES:
            intent.missing_fields.append('currency')
    elif hard.price_min is not None or hard.price_max is not None:
        if hard.currency is not None and hard.currency not in RATES:
            intent.missing_fields.append('currency')
        if intent.required.price_basis != 'unit':
            intent.missing_fields.append('budget_scope')
    if hard.price_basis != 'total' and (hard.quantity_per_product is not None or hard.distinct_count is not None):
        intent.missing_fields.append('bundle_constraints')
    intent.missing_fields = list(dict.fromkeys(intent.missing_fields))
    if not intent.missing_fields and previous_gaps & {'currency', 'budget_scope', 'budget_amount'}:
        intent.action = 'SEARCH'
    if intent.action == 'CLARIFY' and not intent.missing_fields:
        intent.missing_fields = ['details']
    if intent.missing_fields:
        intent.action = 'CLARIFY'
    return intent
