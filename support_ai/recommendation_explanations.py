"""Explain a bound recommendation list using current SKU facts, without a new search."""
import re
from decimal import Decimal, InvalidOperation

from goods.models import SKU
from .contracts import RequiredConditions, QueryConditions
from .pii import redact
from .recommendations import CATEGORY_ALIASES, available_products, product_cards
from .recommendation_options import ORDINAL, number
from .conversation_tasks import tea_mentions
from tea_saas.currency import to_base, BASE_CURRENCY


def _basis(raw):
    if not isinstance(raw, dict):
        return {}
    try:
        return {'required': RequiredConditions.model_validate(raw.get('required', {})).model_dump(),
                'preferred': QueryConditions.model_validate(raw.get('preferred', {})).model_dump(),
                'excluded': QueryConditions.model_validate(raw.get('excluded', {})).model_dump()}
    except ValueError:
        return {}


def _grams(card):
    try:
        value = Decimal(card.get('facts', {}).get('净含量（克）', ''))
        return value if value.is_finite() and 0 < value <= 100000000 else None
    except (InvalidOperation, TypeError, ValueError):
        return None


def format_product_reasons(cards, basis, heading='以下解释上一份商品列表的推荐依据（人民币 CNY 单价，已重新读取当前商品数据）：'):
    basis = _basis(basis)
    required = basis.get('required', {})
    preferred = basis.get('preferred', {})
    prices = [Decimal(c['price']) for c in cards]
    weights = [_grams(c) for c in cards]
    lines = [heading]
    if required.get('currency') not in (None, BASE_CURRENCY):
        lines.append('原预算币种{}按参考比例换算成人民币核对，非实时汇率。'.format(required['currency']))
    canonical = lambda value: CATEGORY_ALIASES.get(value.casefold(), value)
    for index, card in enumerate(cards, 1):
        reasons = []
        if card['category'] in [canonical(v) for v in required.get('categories', [])]:
            reasons.append('属于您要求的{}分类'.format(card['category']))
        elif required.get('categories'):
            reasons.append('当前分类为{}，与原筛选分类不一致，需重新确认'.format(card['category']))
        elif card.get('group_category') == card['category']:
            reasons.append('对应原推荐列表的{}分组'.format(card['category']))
        if card.get('brand') in required.get('brands', []):
            reasons.append('品牌符合您的要求（{}）'.format(card['brand']))
        elif required.get('brands'):
            reasons.append('当前品牌与原筛选品牌不一致，需重新确认')
        names = (card['name'] + ' ' + card['product_name']).casefold()
        keywords = required.get('keywords', [])
        if keywords and all(k.casefold() in names for k in keywords):
            reasons.append('名称包含您指定的关键词：' + '、'.join(keywords))
        price = Decimal(card['price'])
        low, high = required.get('price_min'), required.get('price_max')
        if (required.get('price_basis') == 'unit'
                and (low is not None or high is not None)):
            code = required.get('currency') or BASE_CURRENCY
            if (low is None or price >= to_base(low, code, upper=False)) and (high is None or price <= to_base(high, code)):
                reasons.append('当前每份单价符合已确认预算（按人民币基础价核算）')
            else:
                reasons.append('当前价格已不符合原预算，需要重新确认')
        if card['category'] in [canonical(v) for v in preferred.get('categories', [])]:
            reasons.append('茶类匹配已保存的软偏好')
        if card.get('brand') and card['brand'] in preferred.get('brands', []):
            reasons.append('品牌匹配已保存的软偏好')
        reasons.append('当前上架且有可用库存')
        if len(set(prices)) > 1 and price == min(prices):
            reasons.append('在这份列表中每份售价最低，单份购入成本较低（不代表按克最便宜）')
        grams = weights[index - 1]
        if grams is not None:
            reasons.append('净含量{}克，按当前单价折合约 ¥{:.2f}/100克'.format(grams, price / grams * 100))
            known = [w for w in weights if w is not None]
            if len(known) == len(cards) and len(set(known)) > 1 and grams == min(known):
                reasons.append('在这份列表中净含量最小，若希望先少量尝试可优先考虑')
        facts = card.get('facts', {})
        lines.append('\n{}. {} · {} · ¥{}'.format(index, card['product_name'], card['name'], card['price']))
        if card.get('group_category'):
            lines.append('原推荐分组：' + card['group_category'])
        lines.append('推荐依据：' + '；'.join(reasons) + '。')
        if facts:
            lines.append('已配置属性：' + '；'.join('{}：{}'.format(k, v) for k, v in facts.items()) + '。')
        else:
            lines.append('尚无可验证的风味或包装等属性，无法据此进一步区分。')
    if any('虚拟' in c['product_name'] or any('模拟' in k for k in c.get('facts', {})) for c in cards):
        lines.append('\n以上涉及虚拟商品数据，模拟口感、香气等仅为数据库中的演示属性。')
    lines.append('这些依据限于已确认条件及商品当前数据；尚不能据此认定某款最适合您的口味。价格及库存以下单时为准。')
    return redact('\n'.join(lines))


def explain_existing_products(step, completed, history):
    source = completed[step.product_from].data if step.product_from else next(
        (t for t in reversed(history) if (t['turn_id'] == step.reference_turn_id if step.reference_turn_id
         else t.get('product_references') or t.get('recommendation_groups'))), {})
    references = list(source.get('recommendations') or source.get('product_references') or [])[:12]
    basis = _basis(source.get('recommendation_basis') or source.get('product_intent'))

    def response(status, answer, **data):
        return status, dict(answer=answer, explained_products=[], explanation_status=status,
                            recommendation_basis=basis, **data)

    if not references:
        return response('needs_clarification', '当前会话中没有可定位的推荐商品。请先推荐商品，或明确您要解释的商品名称。')
    if step.reference_position is not None:
        references = references[step.reference_position - 1:step.reference_position]
    group = re.search(r'第' + ORDINAL + r'类', step.request) if step.reference_position is None else None
    index = re.search(r'第' + ORDINAL + r'款', step.request) if step.reference_position is None else None
    if group:
        references = [p for p in references if p.get('group_position') == number(group[1])]
    if index:
        # Within a named group use its order; otherwise use the original list order.
        position = number(index[1]) - 1
        references = references[position:position + 1] if position >= 0 else []
    if not group and not index and step.reference_position is None:
        named = [p for p in references if p.get('product_name') and p['product_name'] in step.request]
        if named:
            references = named
        elif re.search(r'这款|那款|它(?:为|的|呢)|this product|that product', step.request, re.I) and len(references) > 1:
            return response('needs_clarification', '上一份列表中有多款商品，请说明第几款或具体商品名称。')
        elif tea_mentions(step.request):
            if re.search(r'不|没|排除|而|instead|not\b', step.request, re.I):
                return response('needs_clarification', '我可以解释上一份列表中已有商品的依据；请说明希望解释的商品或列表位置。')
            categories = {v['canonical'] for v in tea_mentions(step.request)}
            references = [p for p in references if p.get('category') in categories
                          or any(v['canonical'] in categories for v in tea_mentions(p.get('product_name', '')))]
    if not references:
        return response('needs_clarification', '这个位置在上一份推荐列表中没有可定位的商品，请说明列表中的有效位置。')
    bound = []
    for reference in references:
        sku_id = reference.get('sku_id')
        if type(sku_id) is not int or sku_id <= 0:
            # Compatibility with old server records: exact identity only. Never
            # turn a missing object into a fresh catalog recommendation.
            matches = list(SKU.objects.filter(name=reference.get('name', ''),
                                             spu__name=reference.get('product_name', '')).values_list('pk', flat=True)[:2])
            if len(matches) != 1:
                return response('needs_clarification', '历史名称无法唯一定位该商品，请明确规格或重新获取推荐列表。')
            sku_id = matches[0]
        bound.append((reference, sku_id))
    live = {s.pk: s for s in available_products().filter(pk__in=[pk for _, pk in bound])}
    selected = product_cards([live[pk] for _, pk in bound if pk in live])
    references_by_id = {pk: ref for ref, pk in bound}
    for card in selected:
        for key in ('group_category', 'group_position', 'position_in_group'):
            if key in references_by_id[card['sku_id']]:
                card[key] = references_by_id[card['sku_id']][key]
    unavailable = [redact(ref.get('product_name', '') + ' · ' + ref.get('name', ''))
                   for ref, pk in bound if pk not in live]
    answer = format_product_reasons(selected, basis) if selected else '上一份列表中的商品当前均无法确认在售且有库存，暂无法给出可购推荐理由。'
    if unavailable:
        answer += '\n原列表中以下商品当前不可售或无库存：' + '；'.join(unavailable) + '。'
    return ('success' if selected else 'no_match'), {
        'answer': answer, 'explained_products': selected, 'recommendation_basis': basis,
        'recommendation_references': [dict(ref, sku_id=pk) for ref, pk in bound],
        'explanation_status': 'partial' if selected and unavailable else ('success' if selected else 'no_match'),
        'unavailable_products': unavailable}
