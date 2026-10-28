"""Pure Agent contracts. No Django models, database handles or query expressions."""

import re
from decimal import Decimal, InvalidOperation
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .pii import contains_pii
from tea_saas.currency import RATES


class Contract(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class IntentEvidenceError(ValueError):
    """A content-free field location for one bounded evidence correction."""
    def __init__(self, field, code, message, *, repairable=True):
        super().__init__(message)
        self.field, self.code = field, code
        self.repairable = repairable


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
    budget_mode: Optional[Literal['cap', 'near', 'exact']] = None
    # Extraction checks types only; tool-specific bounds apply after routing.
    quantity_per_product: Optional[int] = Field(default=None, description='仅总价组合的每款购买件数')
    distinct_count: Optional[int] = Field(default=None, description='仅总价组合的不同商品款数；普通推荐用request.limit')
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
    'required.budget_min', 'required.budget_max', 'required.budget_mode', 'required.quantity_per_product', 'required.distinct_count',
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
    context_turn_id: Optional[str] = Field(default=None, max_length=80,
        description='Server-only origin of a contextual budget-scope interpretation; models must leave null.')

    @model_validator(mode='after')
    def contextual_scope_only(self):
        if self.context_turn_id is not None and (self.field != 'required.price_basis'
                or self.value not in ('unit', 'total') or self.source == 'MEMORY'):
            raise ValueError('上下文解释仅适用于预算口径')
        return self


class RecommendationIntent(Contract):
    action: Literal['SEARCH', 'CLARIFY']
    required: RequiredConditions = Field(default_factory=RequiredConditions)
    preferred: QueryConditions = Field(default_factory=QueryConditions)
    excluded: QueryConditions = Field(default_factory=QueryConditions)
    evidence: List[IntentEvidence] = Field(default_factory=list, max_length=40)
    missing_fields: List[Literal[
        'category', 'currency', 'budget_scope', 'budget_amount', 'bundle_constraints',
        'recommendation_count', 'recommendation_scope', 'purchase_quantity',
        'product_reference', 'unsupported_attribute', 'details'
    ]] = Field(default_factory=list, max_length=6)


class ProductRecommendationParameters(Contract):
    """Number of results to display; not a purchase quantity."""
    limit: int = Field(default=4, ge=1, le=4)


class BundleRecommendationParameters(Contract):
    """Applicable only after the server selects recommend_bundle."""
    quantity_per_product: Optional[int] = Field(default=None, ge=1, le=100)
    distinct_count: Optional[int] = Field(default=None, ge=1, le=4)


_UNIT_SCOPE = r'单价|单件(?:商品)?(?:(?:的)?(?:预算|价格))?|每(?:件|盒|包)(?:商品)?(?:(?:的)?(?:预算|价格))?'
_TOTAL_SCOPE = (r'总价|总预算|整套(?:商品)?(?:(?:的)?(?:总)?预算)?|'
                r'套餐(?:(?:的)?(?:总价|总预算|预算))?|整笔采购(?:的)?总预算')
_SCOPE_REPLY = re.compile(
    r'(?:请按|按|是|指的是|我说的是)?\s*(?:(?P<unit>' + _UNIT_SCOPE + r')|(?P<total>' + _TOTAL_SCOPE + r'))'
    r'(?:来推荐|推荐|算|计算)?[。！!？?，,\s]*')


def budget_scope_reply(message):
    """Exact choice wording; the planner still requires a pending scope question."""
    matched = _SCOPE_REPLY.fullmatch(message)
    if matched is None:
        return None
    return ('unit', matched['unit']) if matched['unit'] else ('total', matched['total'])


def _value_supported(field, value, quote):
    if field.endswith('budget_mode'):
        patterns = {'cap': r'不超过|以内|上限|最多|at most|within',
                    'near': r'左右|接近|尽量用满|around|near|approximately',
                    'exact': r'恰好|正好|exactly'}
        return value in patterns and bool(re.search(patterns[value], quote, re.I))
    if field.endswith(('price_min', 'price_max', 'budget_min', 'budget_max')):
        amounts = re.findall(r'(?<![\d.])\d+(?:\.\d{1,2})?(?![\d.])', quote)
        try:
            return any(Decimal(amount) == Decimal(value) for amount in amounts)
        except InvalidOperation:
            return False
    if field.endswith('currency'):
        aliases = {'USD': ('usd', '美元', '美金', '$'), 'AED': ('aed', '迪拉姆'),
                   'SAR': ('sar', '里亚尔'), 'CNY': ('cny', 'rmb', '人民币', '¥', '￥'), 'EUR': ('eur', '欧元', '€')}
        if value == 'CNY' and (re.search(r'(?<![美欧日])元', quote)
                               or quote in ('块', '块钱')
                               or re.search(r'\d\s*块(?:钱)?(?!茶饼|茶砖)', quote)):
            return True
        return any(alias in quote.lower() for alias in aliases[value])
    if field.endswith('price_basis'):
        choice = budget_scope_reply(quote)
        if choice is not None and choice[0] == value:
            return True
        if value == 'unit':
            return bool(re.search(r'每|单价|单件|一盒|一包|一份|一罐|per\b|each\b|unit\b', quote, re.I))
        if value == 'total':
            return bool(re.search(r'总价|总预算|整套|整笔|总共|合计|一共|\btotal\b|\boverall\b', quote, re.I))
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
    if intent.required.price_basis == 'unknown':
        # Unknown is absence of a confirmed scope, not a user assertion that
        # needs a literal quote. Preserve an amount until the scope is resolved.
        for old, new in (('budget_min', 'price_min'), ('budget_max', 'price_max')):
            value = getattr(intent.required, old)
            if value is not None:
                current = getattr(intent.required, new)
                if current is not None and current != value:
                    raise ValueError('未知预算范围的金额字段冲突')
                setattr(intent.required, new, value)
                setattr(intent.required, old, None)
                for item in intent.evidence:
                    if item.field == 'required.' + old:
                        item.field = 'required.' + new
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


def _contextual_scope_supported(item, text, recent_turns):
    """A current pending slot or its saved application interpretation owns scope."""
    if item.field != 'required.price_basis' or item.value not in ('unit', 'total') or item.quote != text:
        return False
    positions = {turn['turn_id']: index for index, turn in enumerate(recent_turns)}
    if item.context_turn_id not in positions:
        return False
    if item.source == 'CURRENT':
        latest = recent_turns[-1]
        state = latest.get('dialogue_state', {})
        return (latest['turn_id'] == item.context_turn_id and state.get('task') == 'recommendation'
                and state.get('status') == 'pending' and 'budget_scope' in state.get('missing_fields', [])
                and state.get('purchase') is not None)
    if item.source != 'CONTEXT' or positions.get(item.source_id, -1) <= positions[item.context_turn_id]:
        return False
    source = recent_turns[positions[item.source_id]]
    expected = {key: getattr(item, key) for key in ('field', 'value', 'quote', 'context_turn_id')}
    return expected in source.get('budget_scope_evidence', [])


def validate_recommendation_intent(intent, message, recent_turns, memory, *, branch_rules=True):
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
        supported = (_contextual_scope_supported(item, text, recent_turns) if item.context_turn_id is not None
                     else _value_supported(item.field, item.value, item.quote))
        if text is None or item.quote not in text or not supported:
            raise IntentEvidenceError(item.field, 'unsupported_evidence', '意向条件无法对应输入证据',
                repairable=item.source == 'CURRENT' and item.context_turn_id is None)
        evidence.setdefault(item.field, []).append(item)

    for name in ('required', 'preferred', 'excluded'):
        section = getattr(intent, name)
        for field, value in section.model_dump().items():
            if name == 'required' and field == 'price_basis' and value == 'unknown':
                continue
            values = value if isinstance(value, list) else ([] if value is None else [value])
            for term in values:
                if not any((Decimal(item.value) == Decimal(term) if field in ('price_min', 'price_max', 'budget_min', 'budget_max')
                            else item.value == str(term)) for item in evidence.get(name + '.' + field, [])):
                    raise IntentEvidenceError(name + '.' + field, 'missing_evidence', '意向条件缺少原文或记忆依据')
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
    if not branch_rules:
        return intent
    # Compatibility for callers that validate a standalone intent. The planner
    # explicitly defers these checks until the application has chosen a tool.
    tool = 'recommend_bundle' if intent.required.price_basis == 'total' else 'recommend_products'
    return validate_recommendation_branch(intent, tool=tool,
        limit=intent.required.distinct_count if intent.required.distinct_count is not None else 4)


def validate_recommendation_branch(intent, *, tool, limit=4):
    """Validate only the selected tool's business parameters, after provenance."""
    intent = RecommendationIntent.model_validate(intent).model_copy(deep=True)
    hard = intent.required
    expected = 'recommend_bundle' if hard.price_basis == 'total' else 'recommend_products'
    if tool != expected:
        raise ValueError('Recommendation parameters do not match the selected tool')
    previous_gaps = set(intent.missing_fields)
    recalculated = {'currency', 'budget_scope', 'budget_amount'}
    if tool == 'recommend_bundle':
        recalculated |= {'recommendation_count', 'recommendation_scope', 'purchase_quantity'}
    else:
        recalculated.add('purchase_quantity')
    intent.missing_fields = [f for f in intent.missing_fields if f not in recalculated]
    if tool == 'recommend_bundle':
        try:
            BundleRecommendationParameters.model_validate({
                'quantity_per_product': hard.quantity_per_product, 'distinct_count': hard.distinct_count})
        except ValueError:
            intent.missing_fields.append('bundle_constraints')
        if hard.budget_max is None or Decimal(hard.budget_max) <= 0:
            intent.missing_fields.append('budget_amount')
        if hard.currency is not None and hard.currency not in RATES:
            intent.missing_fields.append('currency')
    else:
        try:
            ProductRecommendationParameters(limit=limit)
        except ValueError:
            intent.missing_fields.append('recommendation_count')
        legacy_count = hard.distinct_count
        if legacy_count is not None:
            # The result count has already been selected by the server. Do not
            # turn an old model's "one product" slot into a bundle requirement.
            if legacy_count != limit:
                intent.missing_fields.append('recommendation_count')
            hard.distinct_count = None
            intent.evidence = [e for e in intent.evidence if e.field != 'required.distinct_count']
        if 'bundle_constraints' in intent.missing_fields:
            intent.missing_fields.remove('bundle_constraints')
            if legacy_count is None:
                intent.missing_fields.append('recommendation_scope')
        if hard.quantity_per_product is not None:
            intent.missing_fields.append('purchase_quantity')
        if hard.budget_min is not None or hard.budget_max is not None or hard.budget_mode is not None:
            intent.missing_fields.append('budget_scope')
        if hard.price_min is not None or hard.price_max is not None:
            if hard.currency is not None and hard.currency not in RATES:
                intent.missing_fields.append('currency')
            if hard.price_basis != 'unit':
                intent.missing_fields.append('budget_scope')
    intent.missing_fields = list(dict.fromkeys(intent.missing_fields))
    if not intent.missing_fields and previous_gaps & (recalculated | {'bundle_constraints'}):
        intent.action = 'SEARCH'
    if intent.action == 'CLARIFY' and not intent.missing_fields:
        intent.missing_fields = ['details']
    if intent.missing_fields:
        intent.action = 'CLARIFY'
    return intent
