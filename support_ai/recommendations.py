"""Application-owned catalog matching. The Agent never imports this module."""

from django.db.models import Case, Count, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce

from goods.models import SKU, ProductAttributeValue

from .contracts import RecommendationOptions
from .diagnostics import error_diagnostic
from .pii import redact
from .recommendation_options import BASIC_TEA_TYPES
from .recommendation_presentation import product_summary, budget_scope_question
from tea_saas.currency import BASE_CURRENCY, to_base


CLARIFICATIONS = {
    'category': '您想选择哪类茶？',
    'currency': '基础币种为人民币（CNY）。可使用CNY、USD、AED、SAR、EUR；外币按参考比例换算，不是实时汇率。',
    'budget_scope': '这个预算是每份商品的单价，还是整笔采购的商品总预算？',
    'budget_amount': '请说明整套商品总预算上限，例如“总预算200元”；未注明币种按人民币处理。',
    'bundle_constraints': '可以按总预算自动搭配1至4款商品及建议件数；也支持明确指定每款相同的1至100件。不同商品各自指定数量、保留或替换指定商品暂不支持，请调整搭配条件。',
    'recommendation_count': '请明确普通推荐需要返回几款商品，目前支持1至4款；这不是每款的购买件数。',
    'recommendation_scope': '请说明这次是挑选商品，还是按总预算搭配；组合采购条件不能直接作为普通推荐的返回数量。',
    'bundle_quantity': '请说明每款购买几件，或明确允许按预算自动配量。',
    'purchase_quantity': '您提出了每款的购买件数。普通推荐目前只选择商品；如需按采购数量计算总价搭配，请补充商品总预算。',
    'product_reference': '请告诉我具体的商品名称或品类，方便继续筛选。',
    'unsupported_attribute': '暂未找到您所要求的相关信息，无法确认商品是否符合这一条件。您可以查看商品详情或向商家进一步核实。',
    'details': '请说明您想买的品类、品牌或每份商品预算。',
}

from .catalog_terms import CATEGORY_ALIASES


def _match(field, terms):
    query = Q()
    for term in terms:
        # Controlled aliases; never interpret model values as field paths or SQL.
        alias = CATEGORY_ALIASES.get(term.casefold(), term) if field.endswith('catalog__name') else term
        query |= Q(**{field + '__iexact': alias}) | Q(**{field + '__iexact': term})
    return query


def _keyword(term):
    return Q(name__icontains=term) | Q(spu__name__icontains=term)


def available_products():
    from goods.availability import sellable_skus
    return sellable_skus().select_related('spu__catalog', 'spu__brand').annotate(available_stock=F('sellable_stock'))


def product_cards(selected, intent=None):
    """Describe exactly these live SKUs; this helper never selects replacements."""
    fact_names = ('净含量（克）', '包装形式', '配料', '口感', '香气', '产地',
                  '模拟配料', '模拟口感', '模拟香气', '模拟产地国家', '模拟产区')
    attributes = list(ProductAttributeValue.objects.filter(
        Q(sku_id__in=[p.pk for p in selected]) | Q(spu_id__in=[p.spu_id for p in selected], sku__isnull=True),
        attribute__name__in=fact_names,
    ).select_related('attribute').order_by('id')) if selected else []
    cards = []
    for item in selected:
        reasons = []
        if intent is not None:
            if intent.required.categories:
                reasons.append('符合所选分类')
            if intent.required.brands:
                reasons.append('符合所选品牌')
            if intent.required.keywords:
                reasons.append('商品名称包含指定关键词')
            if intent.required.price_basis == 'unit' and (intent.required.price_min is not None or intent.required.price_max is not None):
                reasons.append('单价符合已确认预算（按人民币基础价核算）')
            if getattr(item, 'preference_score', 0):
                reasons.append('匹配部分偏好')
        reasons.append('当前上架且有可用库存')
        facts = {}
        for value in sorted(attributes, key=lambda a:a.sku_id is not None):
            if value.sku_id == item.pk or (value.sku_id is None and value.spu_id == item.spu_id):
                stored = value.get_value()
                if stored is not None and str(stored).strip():
                    facts[redact(value.attribute.name)] = redact(str(stored))[:160]
        cards.append({
            'sku_id':item.id, 'name':redact(item.name), 'product_name':redact(item.spu.name),
            'category':redact(item.spu.catalog.name), 'brand':redact(item.spu.brand.name) if item.spu.brand else '',
            'price':format(item.price,'.2f'), 'currency':BASE_CURRENCY, 'available_stock':item.available_stock,
            'image_url':'/v1/goods/sku/{}/image'.format(item.id),
            'detail_url':'/product_details.html?skuid={}'.format(item.id), 'reasons':reasons, 'facts':facts,
        })
    return cards


def ranked_products(intent, *, unit_prices=True):
    """Shared hard filters and soft scores; total budgets never become SKU floors."""
    # An existing inventory ledger is authoritative. SKU.stock is a legacy fallback
    # only when there is no ledger; reserved/exhausted ledger stock cannot be revived.
    products = available_products()
    for name, field in (('categories', 'spu__catalog__name'), ('brands', 'spu__brand__name')):
        terms = getattr(intent.required, name)
        if terms:
            products = products.filter(_match(field, terms))
        terms = getattr(intent.excluded, name)
        if terms:
            products = products.exclude(_match(field, terms))
    for term in intent.required.keywords:
        products = products.filter(_keyword(term))
    for term in intent.excluded.keywords:
        products = products.exclude(_keyword(term))
    if unit_prices and intent.required.price_min is not None:
        products = products.filter(price__gte=to_base(intent.required.price_min, intent.required.currency, upper=False))
    if unit_prices and intent.required.price_max is not None:
        products = products.filter(price__lte=to_base(intent.required.price_max, intent.required.currency))

    score = Value(0, output_field=IntegerField())
    for name, field in (('categories', 'spu__catalog__name'), ('brands', 'spu__brand__name')):
        terms = getattr(intent.preferred, name)
        if terms:
            score = score + Case(When(_match(field, terms), then=Value(3)), default=Value(0), output_field=IntegerField())
    for term in intent.preferred.keywords:
        score = score + Case(When(_keyword(term), then=Value(1)), default=Value(0), output_field=IntegerField())
    return products.annotate(preference_score=score).order_by(
        '-preference_score', '-is_recommended', '-sales', 'id'
    )


def match_products(intent, limit=4):
    if type(limit) is not int or not 1 <= limit <= 4:
        raise ValueError('Recommendation limit must be 1 to 4')
    if intent.action == 'CLARIFY':
        return {'recommendation_status': 'CLARIFY', 'recommendations': [],
                'answer': ' '.join((budget_scope_question(intent) or CLARIFICATIONS[field])
                                  if field == 'budget_scope' else CLARIFICATIONS[field]
                                  for field in intent.missing_fields)}
    if intent.required.price_basis == 'total':
        raise ValueError('Total budgets require recommend_bundle')
    selected = list(ranked_products(intent)[:limit])
    cards = product_cards(selected, intent)
    if not cards:
        return {'recommendation_status': 'NO_MATCH', 'recommendations': [],
                'answer': '当前没有满足这些条件的可售商品。您可以调整品类、品牌、关键词或预算；我会保留您明确提出的条件。'}
    lines = [product_summary(cards)]
    if intent.required.currency not in (None, BASE_CURRENCY):
        lines.append('输入的{}预算已按参考比例换算成人民币筛选，非实时汇率。'.format(intent.required.currency))
    lines.append('价格及可购买状态以下单时为准。')
    return {'recommendation_status': 'MATCHED', 'recommendations': cards, 'answer': '\n'.join(lines)}


def match_product_groups(intent, options, category_scope=None):
    options = RecommendationOptions.model_validate(options)
    if options.clarification:
        return {'recommendation_status': 'CLARIFY', 'recommendations': [], 'recommendation_groups': [],
                'answer': options.clarification}
    if intent.action == 'CLARIFY':
        return dict(match_products(intent), recommendation_groups=[])
    canonical = lambda value: CATEGORY_ALIASES.get(value.casefold(), value)
    required = list(dict.fromkeys(canonical(v) for v in intent.required.categories))
    if category_scope is not None:
        if any(c not in BASIC_TEA_TYPES for c in category_scope) or len(category_scope) > 6:
            raise ValueError('Invalid trusted knowledge scope')
        categories = [c for c in dict.fromkeys(category_scope) if not required or c in required]
    else:
        categories = required or list(BASIC_TEA_TYPES)
    excluded = {canonical(v) for v in intent.excluded.categories}
    categories = [v for v in categories if v not in excluded]
    if len(categories) > 6 or len(categories) * options.per_category_limit > options.total_limit:
        return {'recommendation_status': 'CLARIFY', 'recommendations': [], 'recommendation_groups': [],
                'answer': '分类推荐最多覆盖 6 类、合计最多 12 款，请减少茶类或每类数量。'}
    cards, groups, diagnostics, unmet = [], [], [], []
    lines = ['按茶类分别推荐，每类最多 {} 款（人民币 CNY 单价，价格及库存以下单时为准）：'.format(options.per_category_limit)]
    if intent.required.currency not in (None, BASE_CURRENCY):
        lines.append('输入的{}预算已按参考比例换算成人民币筛选，非实时汇率。'.format(intent.required.currency))
    for group_index, category in enumerate(categories, 1):
        scoped = intent.model_copy(deep=True)
        scoped.required.categories = [category]
        # Server-owned grouping is applied only after provenance validation of
        # the original intent. All other hard/excluded filters remain intact.
        try:
            data = match_products(scoped, limit=options.per_category_limit)
            status = 'success' if data['recommendations'] else 'no_match'
            selected = data['recommendations']
        except Exception as exc:
            status, selected = 'error', []
            diagnostic = dict(error_diagnostic(exc, 'recommendation.group'), category=category)
            diagnostics.append(diagnostic)
        group = {'position': group_index, 'category': category, 'status': status, 'recommendations': selected}
        groups.append(group)
        lines.append('\n{}. {}'.format(group_index, category))
        if not selected:
            text = '暂无符合条件的可售商品。' if status == 'no_match' else '本类查询暂时失败，其余分类继续展示。'
            lines.append(text)
            unmet.append(category + '：' + text)
        for within, card in enumerate(selected, 1):
            card.update(group_category=category, group_position=group_index, position_in_group=within)
            cards.append(card)
            lines.append('商品 {}：{} · {} · ¥{}'.format(len(cards), card['product_name'], card['name'], card['price']))
            if options.include_reasons:
                lines.append('匹配理由：' + '；'.join(card['reasons']) + '。')
                if card['facts']:
                    lines.append('商品特点（数据库已配置）：' + '；'.join('{}：{}'.format(k, v) for k, v in card['facts'].items()) + '。')
                else:
                    lines.append('该商品未配置可验证的风味等属性，暂无法进一步判断。')
    if not categories:
        lines.append('当前说明范围与筛选条件没有可推荐的茶类交集，请调整条件。')
    if groups and all(g['status'] == 'error' for g in groups):
        overall = 'ERROR'
    elif cards and all(g['status'] == 'success' for g in groups):
        overall = 'MATCHED'
    elif any(g['status'] == 'error' for g in groups) or cards:
        overall = 'PARTIAL'
    else:
        overall = 'NO_MATCH'
    return {'recommendation_status': overall, 'recommendations': cards, 'recommendation_groups': groups,
            'answer': redact('\n'.join(lines)), 'diagnostics': diagnostics, 'unmet_requirements': unmet}
