"""Application-owned catalog matching. The Agent never imports this module."""

from decimal import Decimal

from django.db.models import Case, Count, F, IntegerField, Q, Sum, Value, When
from django.db.models.functions import Coalesce

from goods.models import SKU

from .pii import redact


CLARIFICATIONS = {
    'category': '您想选择哪类茶？',
    'currency': '请用美元说明每份商品的预算，目前推荐按 USD 单价匹配。',
    'budget_scope': '这个预算是每份商品的单价，还是整笔采购的总预算？请说明每份预算。',
    'product_reference': '请告诉我具体的商品名称或品类，方便继续筛选。',
    'unsupported_attribute': '目前只能核对商品分类、品牌、名称和价格。请提供这些筛选条件，口感、功效或认证需向商家确认。',
    'details': '请说明您想买的品类、品牌或每份商品预算。',
}

CATEGORY_ALIASES = {
    'black tea': '红茶', 'green tea': '绿茶', 'white tea': '白茶',
    'oolong tea': '乌龙茶', 'dark tea': '黑茶', 'yellow tea': '黄茶',
}


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
    return SKU.objects.filter(is_launched=True).select_related('spu__catalog', 'spu__brand').annotate(
        ledger_count=Count('inventory'),
        ledger_available=Coalesce(Sum('inventory__available_quantity'), Value(0)),
    ).annotate(available_stock=Case(
        When(ledger_count=0, then=F('stock')), default=F('ledger_available'), output_field=IntegerField(),
    )).filter(available_stock__gt=0)


def match_products(intent, limit=4):
    if type(limit) is not int or not 1 <= limit <= 4:
        raise ValueError('Recommendation limit must be 1 to 4')
    if intent.action == 'CLARIFY':
        return {'recommendation_status': 'CLARIFY', 'recommendations': [],
                'answer': ' '.join(CLARIFICATIONS[field] for field in intent.missing_fields)}

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
    if intent.required.price_min is not None:
        products = products.filter(price__gte=Decimal(intent.required.price_min))
    if intent.required.price_max is not None:
        products = products.filter(price__lte=Decimal(intent.required.price_max))

    score = Value(0, output_field=IntegerField())
    for name, field in (('categories', 'spu__catalog__name'), ('brands', 'spu__brand__name')):
        terms = getattr(intent.preferred, name)
        if terms:
            score = score + Case(When(_match(field, terms), then=Value(3)), default=Value(0), output_field=IntegerField())
    for term in intent.preferred.keywords:
        score = score + Case(When(_keyword(term), then=Value(1)), default=Value(0), output_field=IntegerField())
    selected = list(products.annotate(preference_score=score).order_by(
        '-preference_score', '-is_recommended', '-sales', 'id'
    )[:limit])
    cards = []
    for item in selected:
        reasons = []
        if intent.required.categories:
            reasons.append('符合所选分类')
        if intent.required.brands:
            reasons.append('符合所选品牌')
        if intent.required.keywords:
            reasons.append('商品名称包含指定关键词')
        if intent.required.price_min is not None or intent.required.price_max is not None:
            reasons.append('单价符合美元预算')
        if item.preference_score:
            reasons.append('匹配部分偏好')
        cards.append({
            'sku_id': item.id, 'name': redact(item.name), 'product_name': redact(item.spu.name),
            'category': redact(item.spu.catalog.name),
            'brand': redact(item.spu.brand.name) if item.spu.brand else '',
            'price': format(item.price, '.2f'), 'currency': 'USD',
            'image_url': '/v1/goods/sku/{}/image'.format(item.id),
            'detail_url': '/product_details.html?skuid={}'.format(item.id),
            'reasons': reasons or ['当前上架且有可用库存'],
        })
    if not cards:
        return {'recommendation_status': 'NO_MATCH', 'recommendations': [],
                'answer': '当前没有满足这些条件的可售商品。您可以调整品类、品牌、关键词或预算；我会保留您明确提出的条件。'}
    lines = ['按您的条件找到以下可售商品（USD 单价，价格及库存以下单时为准）：']
    lines.extend('{}. {} · {} · ${} · {}'.format(index, card['product_name'], card['name'], card['price'], '、'.join(card['reasons']))
                 for index, card in enumerate(cards, 1))
    return {'recommendation_status': 'MATCHED', 'recommendations': cards, 'answer': '\n'.join(lines)}
