"""Application-owned, read-only tool handlers; credentials/owners never come from plans."""
import json
import re
from django.db.models import Q

from langchain_core.prompts import ChatPromptTemplate

from goods.models import Catalog, SKU, ProductAttributeValue
from .contracts import RecommendationIntent, validate_recommendation_intent
from .execution import ToolResult
from .diagnostics import error_diagnostic
from .pii import redact
from .recommendations import CATEGORY_ALIASES, available_products, match_products, match_product_groups
from .recommendation_options import BASIC_TEA_TYPES, CATEGORY_PATTERN, DESCRIBED_TEA_REFERENCE, ORDINAL, number
from .tea_explanation import explain_tea_scope
from .planning import explicit_requests
from .conversation_tasks import (purchase_topic, apply_purchase_topic, without_reason_modifier,
                                 REASON_PATTERN)
from .recommendation_explanations import explain_existing_products, format_product_reasons


GENERIC_CATEGORIES = {'茶', '茶叶', '茶类', '商品', '茶品', 'tea', 'teas', 'products', 'tea products'}


def simple_grouped_intent(message, request, history, memory):
    """Recognize only a bounded grouping instruction; unknown qualifiers use extraction."""
    outside = message.replace(request, '', 1)
    if re.search(r'预算|美元|usd|价格|每盒|每包|不要|排除|品牌|不超过|以内', outside, re.I):
        return None
    if any(re.search(r'预算|美元|usd|价格|每盒|每包|不要|排除|品牌|不超过|以内', t['user_text'], re.I)
           for t in history if t.get('intent') in ('recommendation', 'multi_intent')):
        return None
    working = re.sub(DESCRIBED_TEA_REFERENCE, '不同茶类', without_reason_modifier(request))
    data = {'action': 'SEARCH', 'required': {}, 'preferred': {}, 'excluded': {}, 'evidence': []}
    def evidence(field, value, quote):
        data['evidence'].append({'field': field, 'value': value, 'source': 'CURRENT', 'quote': quote})
    budget_pattern = (r'(?:每(?:盒|包|份|罐)(?:商品)?(?:的)?(?:单价)?|单价)\s*'
                      r'(?:不超过|不高于|最多|上限(?:为)?|≤)\s*(\d{1,8}(?:\.\d{1,2})?)\s*(美元|美金|USD|usd)')
    budgets = list(re.finditer(budget_pattern, working))
    if len(budgets) > 1:
        return None
    if budgets:
        match = budgets[0]
        data['required'].update(price_max=match[1], currency='USD', price_basis='unit')
        for field, value in [('price_max', match[1]), ('currency', 'USD'), ('price_basis', 'unit')]:
            evidence('required.' + field, value, match[0])
        working = working[:match.start()] + working[match.end():]
    exclusion_pattern = r'(?:不要|排除)\s*(?:(?:' + CATEGORY_PATTERN + r')\s*(?:[、和及,，]\s*)?)+'
    excluded = []
    for match in re.finditer(exclusion_pattern, working, re.I):
        for category in re.finditer(CATEGORY_PATTERN, match[0], re.I):
            if category[0] not in excluded:
                excluded.append(category[0])
                evidence('excluded.categories', category[0], match[0])
    working = re.sub(exclusion_pattern, '', working, flags=re.I)
    data['excluded']['categories'] = excluded
    remaining = re.sub(CATEGORY_PATTERN, '', working, flags=re.I)
    remaining = re.sub(r'那|我希望|我想|我|希望|你|能|可以|请|根据|按照|按|不同|的|茶叶|茶类|茶|种类|品类|类别|'
                       r'给我|给出|给|进行|一些|一下|商品|推荐|并|理由|原因|分别|每种|每类|各|种|类|款|和|及|、|'
                       r'[一二两三四1234]|[\s，,。；;！？!?]', '', remaining)
    if remaining:
        return None
    categories = list(dict.fromkeys(m[0] for m in re.finditer(CATEGORY_PATTERN, working, re.I)))
    data['required']['categories'] = categories
    for value in categories:
        evidence('required.categories', value, value)
    if memory:
        for field in ('categories', 'brands', 'keywords'):
            data['preferred'][field] = list(memory['preferences'].get(field, []))
            data['evidence'].extend({'field': 'preferred.' + field, 'value': value, 'quote': value,
                                    'source': 'MEMORY', 'source_id': memory['id']}
                                   for value in data['preferred'][field])
    return RecommendationIntent.model_validate(data)


def simple_purchase_intent(message, request, history, memory):
    """Deterministic slots for bounded category-only requests; complex constraints use the model."""
    category_pattern = r'红茶|绿茶|白茶|乌龙茶|黑茶|黄茶|black tea|green tea|white tea|oolong tea|dark tea|yellow tea'
    subject = r'(?:' + category_pattern + r'|茶叶|茶类|茶品|商品|茶|tea|products)'
    simple = (r'(?:(?:请|给我|帮我|再|先|我想|我要|我)?(?:推荐|选|挑|找|买|recommend)'
              r'(?:一|二|两|三|四|[1-4])?(?:款|种|件|个)?(?:适合日常饮用的)?\s*)?' + subject + r'\s*(?:吧)?')
    if not re.fullmatch(simple, without_reason_modifier(request), re.I):
        return None
    if re.search(r'预算|美元|usd|价格|每盒|每包|不要|排除|品牌|不超过|以内', message, re.I):
        return None
    # A previous explicit budget, exclusion or brand must still be interpreted.
    for turn in history:
        if turn.get('intent') in ('recommendation', 'multi_intent') and re.search(
                r'预算|美元|usd|价格|每盒|每包|不要|排除|品牌|不超过|以内', turn['user_text'], re.I):
            return None
    data = {'action': 'SEARCH', 'required': {}, 'preferred': {}, 'evidence': []}
    matches = list(re.finditer(category_pattern, request, re.I))
    source, source_id, quote = 'CURRENT', None, request
    if not matches:
        # A single explicitly named tea in the same mixed request is its shared
        # topic; separately named purchase topics already match above.
        shared = list(re.finditer(category_pattern, message, re.I))
        if len({m[0].casefold() for m in shared}) == 1 and not re.search(r'不要|排除|不是', message):
            matches, quote = shared[:1], message
        else:
            topic = purchase_topic(message, request, history)
            if topic['state'] in ('multiple', 'complex'):
                return None
            if topic['state'] == 'single':
                data['required']['categories'] = [topic['category']]
                data['evidence'].append(topic['evidence'])
    if matches:
        value = matches[0][0]
        data['required']['categories'] = [value]
        data['evidence'].append({'field': 'required.categories', 'value': value, 'source': source,
                                 'source_id': source_id, 'quote': quote})
    if memory:
        for field in ('categories', 'brands', 'keywords'):
            values = memory['preferences'].get(field, [])
            data['preferred'][field] = list(values)
            data['evidence'].extend({'field': 'preferred.' + field, 'value': value, 'quote': value,
                                    'source': 'MEMORY', 'source_id': memory['id']} for value in values)
    return RecommendationIntent.model_validate(data)


def normalize_recommendation(raw, message, history, memory, request):
    """Normalize range words before provenance validation can clear soft preferences."""
    intent = RecommendationIntent.model_validate(raw).model_copy(deep=True)
    for section in ('required', 'preferred'):
        values = getattr(intent, section).categories
        removed = {v for v in values if v.casefold() in GENERIC_CATEGORIES}
        getattr(intent, section).categories = [v for v in values if v not in removed]
        intent.evidence = [e for e in intent.evidence
                           if not (e.field == section + '.categories' and e.value in removed)]
    # The server owns saved preferences. Canonicalize a verified soft preference
    # rather than trusting model-added labels such as "categories: 绿茶" as quotes.
    for evidence in intent.evidence:
        if evidence.source == 'MEMORY':
            parts = evidence.field.split('.')
            if (len(parts) != 2 or parts[0] != 'preferred' or not memory
                    or evidence.source_id != memory['id']
                    or evidence.value not in memory['preferences'].get(parts[1], [])):
                raise ValueError('Unverified saved preference')
            evidence.quote = evidence.value
    daily = bool(re.search(r'日常|每天|\bdaily\b', request, re.I))
    allowed_missing = {'category', 'details'} | ({'unsupported_attribute'} if daily else set())
    hard = intent.required
    if (set(intent.missing_fields) <= allowed_missing and hard.price_min is None
            and hard.price_max is None and not re.search(r'不超过|预算|以内|\d.*(?:美元|元|usd)', request, re.I)):
        intent.missing_fields = []
        intent.action = 'SEARCH'
    intent = validate_recommendation_intent(intent, message, history, memory)
    catalog_names = set(Catalog.objects.values_list('name', flat=True))
    if any(CATEGORY_ALIASES.get(v.casefold(), v) not in catalog_names for v in intent.required.categories):
        intent.action = 'CLARIFY'
        intent.missing_fields = ['category']
    if any(v.casefold() in GENERIC_CATEGORIES for v in intent.excluded.categories):
        intent.action = 'CLARIFY'
        intent.missing_fields = ['details']
    return intent, (['当前商品属性不足以验证“适合日常饮用”，本次仅按已确认条件筛选。'] if daily else [])


def create_tool_handlers(model, knowledge_search, message, resolved_question, history, memory, order_context,
                         knowledge_context_chars=12000, scoped_knowledge_search=None, knowledge_notes=None):
    """All arguments supplied by the authenticated application, never from model tool names."""
    history_json = json.dumps(history, ensure_ascii=False)

    def result(step, status='success', data=None, sources=None, unmet=None):
        return ToolResult(step_id=step.id, tool=step.tool, status=status, data=data or {},
                          sources=sources or [], unmet_requirements=unmet or [])

    def recommend(step, completed):
        linked_scope = None
        if step.knowledge_from:
            linked_scope = completed[step.knowledge_from].data.get('explained_categories', [])
        elif re.search(DESCRIBED_TEA_REFERENCE, step.request):
            linked_scope = next((t['explained_categories'] for t in reversed(history) if t.get('explained_categories')), [])
        if linked_scope is not None and (not linked_scope or any(c not in BASIC_TEA_TYPES for c in linked_scope)):
            return result(step, 'needs_clarification', {'answer': '尚无可验证的茶类说明范围，请先说明具体茶类，或先让我介绍茶类区别。',
                          'recommendations': [], 'recommendation_status': 'CLARIFY'})
        prompt = ChatPromptTemplate.from_messages([
            ('system', '提取当前购买子任务的条件，严格输出结构。不得生成商品ID、SQL、价格或库存事实。'
             '完整本轮可能包含知识介绍，不把介绍对象自动当作购买硬条件。'
             '当前购买要求优先于本会话仍有效的购买条件，再考虑长期软偏好。'
             'required是硬条件，preferred是软偏好，excluded是排除项。每个非空字段必须有原文evidence：'
             'CURRENT引用本轮原话，source_id为空；CONTEXT只引用历史用户原话的turn_id；'
             'MEMORY只能用于preferred，quote/value来自所给偏好，source_id使用偏好id。'
             '不能把助手回答或商品列表伪装成用户证据。分类品牌保留原文；茶叶/商品是范围词，不是硬分类。'
             'evidence.field仅允许required.categories/brands/keywords/price_min/price_max/currency/price_basis、'
             'preferred.categories/brands/keywords、excluded.categories/brands/keywords。'
             '每个数组元素独立给证据，路径必须是required.categories，不能带[0]、.0等索引；'
             '数量、limit、推荐理由、action、missing_fields都不是筛选字段，不得为它们生成evidence。'
             '例如用户说推荐白茶，证据为field=required.categories,value=白茶,source=CURRENT,quote=白茶,source_id=null。'
             '宽泛推荐可以SEARCH，不必先问预算或品类。价格须十进制字符串，币种须原文确认，'
             '按不同茶类推荐属于程序负责的分组，不要从助手的介绍中填入六类硬条件；'
             '只有用户原话明确列出的具体分类才可成为required.categories。'
             '每盒/包/份/单价才是unit；总预算或不明单位用CLARIFY。'
             '口感功效认证等无属性证据时标unsupported_attribute，不编造。'
             '日常饮用只是尚待验证的用途，可以先按明确茶类搜索，不虚构适用性。'),
            ('human', '购买子任务：{request}\n本轮原话：{message}\n指代补全（不作为原文证据）：{resolved}\n安全历史：{history}\n长期偏好：{memory}\n契约修正要求：{repair}'),
        ])
        options = step.recommendation
        if linked_scope is not None:
            options = options.model_copy(update={'mode': 'by_category'})
        if options and options.clarification:
            return result(step, 'needs_clarification', {'answer': options.clarification,
                          'recommendations': [], 'recommendation_status': 'CLARIFY'})
        topic = purchase_topic(message, step.request, history) if linked_scope is None and not (
            options and options.mode == 'by_category') else {'state': 'none'}
        if topic['state'] == 'multiple':
            return result(step, 'needs_clarification', {
                'answer': '刚才涉及{}，您希望推荐哪一类，还是这些茶类都推荐？'.format('、'.join(topic['categories'])),
                'recommendations': [], 'recommendation_status': 'CLARIFY'})
        diagnostics, extraction_attempts, extraction_source = [], 0, 'rules'
        try:
            raw = simple_grouped_intent(message, step.request, history, memory) if options and options.mode == 'by_category' else None
            raw = raw if raw is not None else simple_purchase_intent(message, step.request, history, memory)
            extraction_source = 'rules' if raw is not None else 'model'
            if raw is not None:
                intent, unmet = normalize_recommendation(apply_purchase_topic(raw, topic), message, history, memory, step.request)
            else:
                for attempt in range(2):
                    extraction_attempts += 1
                    try:
                        raw = (prompt | model.with_structured_output(RecommendationIntent)).invoke(
                            {'request': step.request, 'message': message, 'history': history_json,
                             'resolved': resolved_question, 'memory': json.dumps(memory, ensure_ascii=False),
                             'repair': json.dumps(diagnostics[-1], ensure_ascii=False) if diagnostics else '无；首次提取'})
                        raw = RecommendationIntent.model_validate(raw)
                        intent, unmet = normalize_recommendation(apply_purchase_topic(raw, topic), message, history, memory, step.request)
                        break
                    except ValueError as exc:
                        diagnostics.append(error_diagnostic(exc, 'recommendation.conditions'))
                        if attempt == 1:
                            raise
        except ValueError as exc:
            diagnostic = error_diagnostic(exc, 'recommendation.conditions')
            if not diagnostics or diagnostics[-1] != diagnostic:
                diagnostics.append(diagnostic)
            return result(step, 'error', {
                'answer': '推荐条件处理暂时异常，请稍后重试。', 'recommendations': [],
                'recommendation_status': 'ERROR', 'condition_source': extraction_source,
                'extraction_attempts': extraction_attempts, 'diagnostics': diagnostics})
        if options and options.mode == 'by_category':
            options = options.model_copy(update={'category_scope': 'requested' if linked_scope is not None or intent.required.categories else 'basic_tea_types'})
        data = match_product_groups(intent, options, category_scope=linked_scope) if options and options.mode == 'by_category' else match_products(intent, limit=step.limit)
        unmet += data.get('unmet_requirements', [])
        data['product_intent'] = intent.model_dump()
        data['condition_source'] = extraction_source
        data['extraction_attempts'] = extraction_attempts
        data['diagnostics'] = data.get('diagnostics', []) + diagnostics
        data['topic_inheritance'] = topic.get('evidence') if topic['state'] == 'single' else None
        data['recommendation_options'] = options.model_dump() if options else None
        data['memory_used'] = any(e.source == 'MEMORY' and e.value in getattr(intent.preferred, e.field.split('.')[-1], [])
                                  for e in intent.evidence)
        data['selected_product'] = data['recommendations'][0] if len(data['recommendations']) == 1 else None
        if data['recommendations'] and REASON_PATTERN.search(step.request):
            data['answer'] = format_product_reasons(data['recommendations'], intent.model_dump(),
                                                  heading='以下是本次推荐及依据（USD 单价，价格及库存以下单时为准）：')
        if unmet:
            data['answer'] += '\n' + ' '.join(unmet)
        status = {'MATCHED': 'success', 'PARTIAL': 'success', 'ERROR': 'error', 'NO_MATCH': 'no_match', 'CLARIFY': 'needs_clarification'}[data['recommendation_status']]
        return result(step, status, data, unmet=unmet)

    def introduce(step, completed):
        if step.tea_scope:
            try:
                data, sources = explain_tea_scope(model, knowledge_search, step.request, step.tea_scope,
                                                  context_chars=knowledge_context_chars, scoped_search=scoped_knowledge_search)
            except ValueError as exc:
                return result(step, 'no_match', {'answer': '茶类说明未通过证据校验，暂不据此推荐商品。',
                              'explained_categories': [], 'diagnostics': [error_diagnostic(exc, 'knowledge.explanation')]})
            return result(step, 'success' if data['explained_categories'] else 'no_match', data, sources=sources,
                          unmet=['{}：说明证据不足，未纳入对应推荐。'.format(c) for c in data['unexplained_categories']])
        # Use the grounded standalone question for every single knowledge task,
        # including ellipses without a small hard-coded pronoun vocabulary.
        # Mixed tasks keep their subtask scope; never feed a purchase clause into
        # knowledge retrieval just because another clause contains a pronoun.
        requests = explicit_requests(message)
        query = (resolved_question if history and len(requests) <= 1
                 and resolved_question != message else step.request)
        evidence = knowledge_search(query) if knowledge_search else []
        if not evidence:
            return result(step, 'no_match', {'answer': '本次未检索到足够的知识证据，暂无法可靠介绍该主题。'})
        notes = knowledge_notes() if knowledge_notes else []
        return result(step, data={'question': query, 'evidence': evidence, 'evidence_limitations': notes}, sources=[
            {'title': e['source_title'], 'url': e['source_reference'], 'year': e.get('metadata', {}).get('year')}
            for e in evidence], unmet=notes)

    def product_details(step, completed):
        source = completed[step.product_from].data if step.product_from else next(
            (t for t in reversed(history) if t.get('product_references') or t.get('recommendation_groups')), {})
        selected = list(source.get('recommendations', source.get('product_references', [])))
        group_match = re.search(r'第' + ORDINAL + r'类', step.request)
        index_match = re.search(r'第' + ORDINAL + r'款', step.request)
        if group_match:
            group_index = number(group_match[1])
            selected = [p for p in selected if p.get('group_position') == group_index]
            if not selected and any(g.get('position') == group_index for g in source.get('recommendation_groups', [])):
                return result(step, 'no_match', {'answer': '所指茶类在上一轮没有可定位的商品，请重新推荐该类商品。'})
        if index_match:
            index = number(index_match[1]) - 1
            selected = selected[index:index + 1] if index >= 0 else []
        if len(selected) != 1:
            return result(step, 'needs_clarification', {'answer': '您希望了解哪一款商品？请说明商品名称或列表中的位置。'})
        if not step.product_from:
            # Historical names identify an object, never its live price/stock.
            matches = list(SKU.objects.filter(name=selected[0]['name'], spu__name=selected[0]['product_name'])[:2])
            if len(matches) != 1:
                return result(step, 'needs_clarification', {'answer': '该名称无法唯一定位商品，请重新推荐或明确商品名称。'})
            selected = [{'sku_id': matches[0].pk}]
        sku = available_products().filter(pk=selected[0]['sku_id']).first()
        if sku is None:
            return result(step, 'no_match', {'answer': '所指商品当前未上架或没有可用库存，请重新选择。'})
        attributes = list(ProductAttributeValue.objects.filter(
            Q(sku=sku) | Q(spu=sku.spu, sku__isnull=True)
        ).values('attribute__name', 'value_text', 'value_number', 'value_boolean', 'value_date'))
        attributes = [{k: redact(v) if isinstance(v, str) else v for k, v in row.items()} for row in attributes]
        data = {'sku_id': sku.pk, 'product_name': redact(sku.spu.name), 'specification': redact(sku.name),
                'category': redact(sku.spu.catalog.name), 'price': str(sku.price), 'currency': 'USD',
                'available_stock': sku.available_stock, 'attributes': json.loads(json.dumps(attributes, default=str))}
        return result(step, data=data, unmet=[] if attributes else ['该商品未配置可验证的风味、用途等结构化属性。'])

    def orders(step, completed):
        return result(step, data={'question': step.request, 'orders': json.loads(order_context)})

    def explain_recommendations(step, completed):
        status, data = explain_existing_products(step, completed, history)
        return result(step, status, data)

    def clarify(step, completed):
        return result(step, 'needs_clarification', {'answer': '您希望了解茶叶知识、挑选商品，还是查询订单？请补充具体对象或要求。'})

    return {'recommend_products': recommend, 'explain_recommendations': explain_recommendations, 'introduce_tea': introduce,
            'get_product_details': product_details, 'get_order_status': orders, 'ask_clarification': clarify}
