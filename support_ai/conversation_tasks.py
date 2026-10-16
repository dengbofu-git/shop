"""Deterministic follow-up classification and user-text-only tea topic evidence."""
import re

from .recommendation_options import CATEGORY_PATTERN, TEA_ALIASES


REASON_PATTERN = re.compile(
    r'推荐(?:的)?(?:理由|原因)|(?:为什么|为何|为啥)(?:要|会)?推荐|'
    r'(?:给出|说明|解释|提供|说说)(?:一下)?(?:推荐)?(?:理由|原因)|'
    r'(?:解释|说明|给出|说说)(?:一下)?(?:这些|这几款|这款|那款)?推荐[^\n，,。；;！？!?]{0,40}(?:理由|原因)|'
    r'(?:解释|说明|给出|说说).{0,20}(?:这几款|这些商品|这款商品|刚才|上次|之前).{0,20}(?:理由|原因)|'
    r'\bwhy\s+(?:did\s+you\s+|do\s+you\s+)?recommend|\breasons?\s+for\s+(?:these\s+)?recommendations?', re.I)
PREVIOUS_RECOMMENDATION = re.compile(r'上次|之前|先前|此前|上一轮|previous|last recommendation', re.I)
RESET_TOPIC = re.compile(r'不限(?:茶类|品类|种类)|所有(?:茶类|商品)|全部商品|随便推荐|换个话题|any tea|all products', re.I)
REASON_MODIFIER = re.compile(r'(?:[，,。；;]?\s*(?:并且|并|再|同时)?\s*(?:请)?'
    r'(?:给出|说明|解释|提供)(?:一下)?(?:推荐)?(?:理由|原因))\s*[。！？!?]*$')


def without_reason_modifier(text):
    return REASON_MODIFIER.sub('', text).strip()


def tea_mentions(text):
    values = []
    for match in re.finditer(CATEGORY_PATTERN, text, re.I):
        raw = match[0]
        canonical = TEA_ALIASES.get(raw.casefold(), raw)
        if canonical not in [v['canonical'] for v in values]:
            values.append({'value':raw, 'canonical':canonical})
    return values


def latest_tea_topic(history):
    """Never promote assistant prose, product cards or long-term memory to intent."""
    for turn in reversed(history):
        text = turn.get('user_text', '')
        if RESET_TOPIC.search(text):
            return {'state':'none'}
        mentions = tea_mentions(text)
        if mentions:
            # Do not infer a new hard constraint from a comparison, exclusion,
            # cancellation or change request whose scope needs interpretation.
            if re.search(r'不要|排除|不买|不想|不是|别推荐|换成|instead|exclude|without|not\b', text, re.I):
                return {'state':'complex'}
            if len(mentions) != 1:
                return {'state':'multiple', 'categories':[m['canonical'] for m in mentions]}
            if not turn.get('turn_id'):
                return {'state':'complex'}
            return {'state':'single', 'category':mentions[0]['value'],
                    'evidence':{'field':'required.categories','value':mentions[0]['value'],
                                'source':'CONTEXT','source_id':turn['turn_id'],'quote':mentions[0]['value']}}
        # A new broad knowledge discussion ends an older specific tea topic.
        if turn.get('intent') == 'question_answering' and re.search(r'茶叶|茶类|茶知识|tea', text, re.I):
            return {'state':'none'}
    return {'state':'none'}


def purchase_topic(message, request, history):
    # Explicit current subjects and scopes always win, including a shared topic
    # in a mixed current-turn instruction. Grouping owns its separate scope.
    if tea_mentions(message) or RESET_TOPIC.search(message):
        return {'state':'none'}
    if re.search(r'换(?:一|个|种|类)|别的(?:茶|种类|分类)|其他茶类|不要|不想|不买|instead|another (?:tea|type)', message, re.I):
        return {'state':'complex'}
    if re.search(r'不同|各种|每类|每种|各类|different tea|each (?:tea|category)', request, re.I):
        return {'state':'none'}
    return latest_tea_topic(history)


def apply_purchase_topic(intent, topic):
    """A server-selected recent user topic overrides model guesses from older turns."""
    if topic.get('state') != 'single':
        return intent
    intent = intent.model_copy(deep=True)
    intent.required.categories = [topic['category']]
    intent.evidence = [e for e in intent.evidence if e.field != 'required.categories']
    # The ordinary provenance validator still checks this exact historic quote.
    from .contracts import IntentEvidence
    intent.evidence.append(IntentEvidence.model_validate(topic['evidence']))
    return intent
