"""Short presentation generated from the same immutable facts as product cards."""
from decimal import Decimal

from .pii import redact


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
