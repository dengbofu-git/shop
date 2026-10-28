"""Short presentation generated from the same immutable facts as product cards."""
from decimal import Decimal, InvalidOperation

from .pii import redact
from .contracts import RequiredConditions, QueryConditions
from .catalog_terms import CATEGORY_ALIASES
from tea_saas.currency import to_base, BASE_CURRENCY


def budget_scope_question(intent):
    hard = intent.required
    amount = hard.price_max or hard.budget_max
    if amount is None:
        return None
    code = hard.currency or 'CNY'
    amount = format(Decimal(amount), 'f').rstrip('0').rstrip('.') if '.' in amount else amount
    return '您说的{}{}，是每件商品的预算，还是整套商品的总预算？'.format(
        '人民币' if code == 'CNY' else code + ' ', amount)


def shopping_reasons(card):
    facts = card.get('facts', {})
    reasons = []
    weight = facts.get('净含量（克）')
    if weight:
        reasons.append('每件{}克'.format(weight))
    package = facts.get('包装形式')
    if package:
        reasons.append(str(package))
    reasons.extend(r for r in card.get('reasons', []) if r not in (
        '当前上架且有可用库存', '本套商品合计符合您的总预算', '符合所选分类'))
    return list(dict.fromkeys(redact(r) for r in reasons))[:2]


def product_summary(cards):
    if not cards:
        return ''
    if len(cards) == 1:
        card = cards[0]
        reasons = shopping_reasons(card)
        detail = '，'.join(reasons)
        return redact('可以先看看{}{}。规格和价格在下方，方便您确认。'.format(
            card['product_name'], '，' + detail if detail else ''))
    cheapest = min(cards, key=lambda c: Decimal(c['price']))
    return redact('这{}款符合您这次的筛选条件。其中{}的单件价格较低，您可以结合下方的规格和价格比较。'.format(
        len(cards), cheapest['product_name']))


def bundle_summary(bundle, budget, *, automatic):
    items = bundle['items']
    units = sum(item['quantity'] for item in items)
    categories = list(dict.fromkeys(item['category'] for item in items))
    scope = categories[0] if len(categories) == 1 else '茶品'
    remaining = Decimal(budget) - Decimal(bundle['subtotal'])
    opening = ('这套搭配有{}款{}，共{}件，商品合计¥{}。'.format(len(items), scope, units, bundle['subtotal']))
    if remaining > 0:
        opening += '比预算少¥{}。'.format(format(remaining, '.2f'))
    else:
        opening += '刚好在这次预算内。'
    if automatic:
        opening += '\n下方件数是按预算和可售库存给出的建议，您也可以告诉我希望购买的数量。'
    else:
        opening += '\n已按您指定的每款件数计算。'
    return redact(opening)


# Bound product explanations operate on public DTOs only.


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
        details = shopping_reasons(card)
        if details:
            lines.append('商品信息：' + '；'.join(details) + '。')
    if any('虚拟' in c['product_name'] or any('模拟' in k for k in c.get('facts', {})) for c in cards):
        lines.append('\n以上涉及虚拟商品数据，模拟口感、香气等仅为数据库中的演示属性。')
    lines.append('这些依据限于已确认条件及商品当前数据；尚不能据此认定某款最适合您的口味。价格及库存以下单时为准。')
    return redact('\n'.join(lines))
