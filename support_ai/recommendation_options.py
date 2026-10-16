"""Server-owned tea groups and bounded recommendation options, never model plans."""
import re

from .contracts import RecommendationOptions

BASIC_TEA_TYPES = ('绿茶', '红茶', '白茶', '乌龙茶', '黄茶', '黑茶')
CATEGORY_PATTERN = r'乌龙茶|绿茶|红茶|白茶|黄茶|黑茶|black tea|green tea|white tea|oolong tea|dark tea|yellow tea'
ORDINAL = r'([一二两三四五六七八九十]{1,3}|\d{1,2})'
DESCRIBED_TEA_REFERENCE = (r'(?:(?:具体|刚才|前面|上述|以上|所|已经|已)(?:的)?)?'
                           r'(?:介绍|说明|讲解|解释|阐述)(?:过)?的(?:这些|这几种)?(?:茶叶种类|茶种|茶类|茶叶|品种)|'
                           r'(?:上述|以上|这些|这几种|所述)(?:的)?(?:茶种|茶类|茶叶)|对应(?:的)?(?:茶种|茶类|商品)')
TEA_ALIASES = dict(zip(('green tea', 'black tea', 'white tea', 'oolong tea', 'yellow tea', 'dark tea'), BASIC_TEA_TYPES))


def tea_scope(request):
    """Only manufacturing tea types are in this catalog; botanical cultivars are distinct."""
    if re.search(r'茶树品种|栽培品种|cultivar', request, re.I):
        return []
    names = list(dict.fromkeys(TEA_ALIASES.get(m[0].casefold(), m[0])
                              for m in re.finditer(CATEGORY_PATTERN, request, re.I)))
    if names:
        return names
    if re.search(r'(?:不同|各种|各类|六大|六种|六类|基本).{0,6}(?:茶种|茶类|茶叶|茶的种类)|different tea types', request, re.I):
        return list(BASIC_TEA_TYPES)
    return []


def number(text):
    digits = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5, '六': 6,
              '七': 7, '八': 8, '九': 9, '十': 10}
    if text.isdigit():
        return int(text)
    if text in digits:
        return digits[text]
    if text.startswith('十') and text[1:] in digits:
        return 10 + digits[text[1:]]
    return 0


def recommendation_options(request):
    grouped = bool(re.search(
        r'不同(?:的)?(?:茶叶|茶)?(?:种类|品类|类别|茶类|茶种)|(?:每|各)(?:一)?(?:种|类)(?:茶叶|茶)?|'
        r'(?:按|根据).{0,16}(?:茶类|茶叶种类|茶叶分类)|各(?:推荐)?[一二两三四五六七八九十\d]+款|'
        r'分别.{0,6}推荐|六(?:大|种|类)茶(?:类|叶)?|\b(?:different tea types|each tea type|by tea type)\b', request, re.I))
    if not grouped:
        count = re.search(r'(?:推荐|选|挑|找)\s*' + ORDINAL + r'\s*款', request)
        issue = '单次普通推荐最多 4 款，请调整数量。' if count and number(count[1]) > 4 else ''
        return RecommendationOptions(clarification=issue)
    count = re.search(r'(?:每(?:种|类)(?:茶叶|茶)?(?:各)?(?:推荐)?|各(?:推荐)?)\s*' + ORDINAL + r'\s*款', request)
    per_category = number(count[1]) if count else 1
    explicit = bool(re.search(CATEGORY_PATTERN, request, re.I))
    issue = ''
    if not 1 <= per_category <= 4:
        issue = '分类推荐每类最多 4 款、合计最多 12 款，请调整推荐数量。'
    # A total count is a different constraint from a count per group; do not guess.
    if re.search(r'总共|一共|合计|总计', request):
        issue = '请说明希望覆盖哪些茶类及每类几款；分类推荐每类最多 4 款、合计最多 12 款。'
    count_free = request[:count.start()] + request[count.end():] if count else request
    if re.search(r'(?:推荐|选|挑|找)\s*' + ORDINAL + r'\s*款', count_free):
        issue = '您希望每类分别推荐，还是所有茶类合计指定数量？请说明每类数量。'
    return RecommendationOptions(mode='by_category', category_scope='requested' if explicit else 'basic_tea_types',
                                 per_category_limit=min(4, max(1, per_category)), clarification=issue)
