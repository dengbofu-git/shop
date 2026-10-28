"""High precision total-budget slots. Unknown wording stays with the planner."""
import re

from .contracts import RecommendationIntent


AMOUNT = r'(?:0|[1-9]\d{0,7})(?:\.\d{1,2})?'
TOTAL = r'整笔采购的总预算|整笔采购总预算|商品总预算|总预算|总价|合计|总共|一共'
CURRENCY = r'美元|美金|USD|usd|人民币|CNY|cny|RMB|rmb|迪拉姆|AED|aed|里亚尔|SAR|sar|欧元|EUR|eur|块钱|块|元钱|元|¥|￥|€|\$'
CATEGORY = r'绿茶|红茶|白茶|乌龙茶|黄茶|黑茶'
NUMBERS = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4}


def simple_money_intent(message):
    """A bounded amount-only request is understood, but its price scope is not guessed."""
    match = re.fullmatch(
        r'(?:请|给我|帮我|我想)?推荐\s*(?P<amount>' + AMOUNT + r')\s*'
        r'(?P<currency>块钱|块|元钱|元|人民币|CNY|cny|RMB|rmb)\s*'
        r'(?P<mode>左右|以内|以下)?\s*的\s*(?P<category>' + CATEGORY + r'|茶叶|茶)'
        r'[。！!？?，,\s]*', message)
    if match is None:
        return None
    evidence = [dict(field='required.' + field, value=value, source='CURRENT', quote=quote)
                for field, value, quote in (
                    ('price_max', match['amount'], match['amount']),
                    ('currency', 'CNY', match['currency']),
                    ('price_basis', 'unknown', match[0]))]
    hard = {'price_max': match['amount'], 'currency': 'CNY', 'price_basis': 'unknown'}
    if match['category'] not in ('茶', '茶叶'):
        hard['categories'] = [match['category']]
        evidence.append(dict(field='required.categories', value=match['category'], source='CURRENT', quote=match['category']))
    if match['mode'] == '左右':
        hard['budget_mode'] = 'near'
        evidence.append(dict(field='required.budget_mode', value='near', source='CURRENT', quote=match['mode']))
    return RecommendationIntent(action='CLARIFY', required=hard, evidence=evidence, missing_fields=['budget_scope'])


def simple_total_intent(message, *, allow_supplement=False):
    working = message
    data = {'action': 'SEARCH', 'required': {}, 'evidence': []}
    hard = data['required']

    def evidence(field, value, quote):
        data['evidence'].append({'field': 'required.' + field, 'value': str(value),
                                 'source': 'CURRENT', 'quote': quote})

    pattern = (r'(?P<scope>' + TOTAL + r')\s*(?:是|为|在|改成|改为|不超过|最多|上限为|上限)?\s*'
               r'(?P<prefix_currency>' + CURRENCY + r')?\s*(?P<low>' + AMOUNT + r')'
               r'(?:\s*(?:至|到|[-~～])\s*(?P<high>' + AMOUNT + r'))?'
               r'\s*(?P<currency>' + CURRENCY + r')?(?![\d.])')
    budgets = list(re.finditer(pattern, working))
    if len(budgets) > 1:
        return None
    if budgets:
        found = budgets[0]
        hard['price_basis'] = 'total'
        evidence('price_basis', 'total', found['scope'])
        hard['budget_max'] = found['high'] or found['low']
        evidence('budget_max', hard['budget_max'], found[0])
        if found['high']:
            hard['budget_min'] = found['low']
            evidence('budget_min', hard['budget_min'], found[0])
        # Keep currency in the residual text for separate, exact provenance.
        working = working[:found.start()] + ' ' + (found['prefix_currency'] or '') + ' ' + (found['currency'] or '') + working[found.end():]
    else:
        scope = re.search(TOTAL, working)
        if scope:
            hard['price_basis'] = 'total'
            evidence('price_basis', 'total', scope[0])
            working = working[:scope.start()] + working[scope.end():]
        elif not allow_supplement:
            return None

    currencies = list(re.finditer(CURRENCY, working))
    mode = re.search(r'恰好|正好|左右|尽量接近|接近|尽量用满', working)
    if mode and hard.get('price_basis') == 'total':
        hard['budget_mode'] = 'exact' if mode[0] in ('恰好', '正好') else 'near'
        evidence('budget_mode', hard['budget_mode'], mode[0])
        if hard['budget_mode'] == 'exact' and hard.get('budget_max') is not None:
            hard['budget_min'] = hard['budget_max']
            evidence('budget_min', hard['budget_min'], budgets[0][0])
        working = working[:mode.start()] + working[mode.end():]
    aliases = {'美元': 'USD', '美金': 'USD', '$': 'USD', '人民币': 'CNY', '元': 'CNY', '元钱': 'CNY',
               '块': 'CNY', '块钱': 'CNY', '¥': 'CNY', '￥': 'CNY',
               'RMB': 'CNY', 'rmb': 'CNY', '迪拉姆': 'AED', '里亚尔': 'SAR', '欧元': 'EUR', '€': 'EUR'}
    values = {aliases.get(m[0], m[0].upper()) for m in currencies}
    if len(values) > 1:
        return None
    if currencies:
        hard['currency'] = next(iter(values))
        evidence('currency', hard['currency'], currencies[0][0])
        working = re.sub(CURRENCY, '', working)

    categories = list(dict.fromkeys(re.findall(CATEGORY, working)))
    if categories:
        hard['categories'] = categories
        for category in categories:
            evidence('categories', category, category)
        working = re.sub(CATEGORY, '', working)
    quantities = list(re.finditer(r'每款(?:购买|买)?\s*([一二两三四]|[1-9]\d?)\s*件', working))
    if len(quantities) > 1:
        return None
    if quantities:
        q = quantities[0]
        hard['quantity_per_product'] = NUMBERS.get(q[1], int(q[1]) if q[1].isdigit() else 0)
        evidence('quantity_per_product', hard['quantity_per_product'], q[0])
        working = working[:q.start()] + working[q.end():]
    counts = list(re.finditer(r'([一二两三四1-4])\s*款', working))
    if len(counts) > 1:
        return None
    if counts:
        count = counts[0]
        hard['distinct_count'] = NUMBERS.get(count[1], int(count[1]) if count[1].isdigit() else 0)
        evidence('distinct_count', hard['distinct_count'], count[0])
        working = working[:count.start()] + working[count.end():]
    remaining = re.sub(r'我希望|我想|希望|请|帮我|给我|推荐|搭配|选|一些|一下|茶叶|茶品|商品|和|与|及|'
                       r'左右|以内|之内|整套|整笔采购|的|是|为|吧|[\s，,。；;！？!?、]', '', working)
    # A generic scope is not a leftover qualifier. Consume only the whole
    # residual noun, so compounds such as 有机茶/茶饼 keep their constraints.
    if remaining in ('茶', '套餐'):
        remaining = ''
    if remaining or not hard or (not budgets and not allow_supplement and hard.get('price_basis') != 'total'):
        return None
    if re.search(r'尽量用满', message):
        hard['quantity_policy'] = 'automatic'
        evidence('quantity_policy', 'automatic', '尽量用满')
    return RecommendationIntent.model_validate(data)
