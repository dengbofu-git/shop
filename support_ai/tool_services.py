"""Application-owned, read-only tool handlers; credentials/owners never come from plans."""
import json
import re

from langchain_core.prompts import ChatPromptTemplate

from .contracts import (RecommendationIntent, validate_recommendation_intent,
                        validate_recommendation_branch)
from .execution import ToolResult
from .diagnostics import error_diagnostic
from .pii import redact
from .catalog_terms import MISSING_ATTRIBUTES
from .recommendation_options import BASIC_TEA_TYPES, CATEGORY_PATTERN, DESCRIBED_TEA_REFERENCE, ORDINAL, number
from .tea_explanation import explain_tea_scope
from .planning import explicit_requests
from .conversation_tasks import (purchase_topic, apply_purchase_topic, without_reason_modifier,
                                 REASON_PATTERN)
from .recommendation_presentation import format_product_reasons
from .total_budget_intent import CURRENCY
from .order_contracts import rule_order_query
from .grounding import generate_grounded_answer
from .bundle_references import bundle_products


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
                      r'(?:不超过|不高于|最多|上限(?:为)?|≤)\s*(\d{1,8}(?:\.\d{1,2})?)\s*(' + CURRENCY + r')?')
    budgets = list(re.finditer(budget_pattern, working))
    if len(budgets) > 1:
        return None
    if budgets:
        match = budgets[0]
        data['required'].update(price_max=match[1], price_basis='unit')
        currency_aliases = {'美元':'USD', '美金':'USD', '$':'USD', '人民币':'CNY', '元':'CNY', '¥':'CNY', '￥':'CNY',
                            'RMB':'CNY', '迪拉姆':'AED', '里亚尔':'SAR', '欧元':'EUR', '€':'EUR'}
        if match[2]:
            code = currency_aliases.get(match[2], currency_aliases.get(match[2].upper(), match[2].upper()))
            data['required']['currency'] = code
            evidence('required.currency', code, match[0])
        for field, value in [('price_max', match[1]), ('price_basis', 'unit')]:
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


def normalize_recommendation(raw, message, history, memory, request, *, tool=None, limit=4, data_access=None):
    """Normalize range words before provenance validation can clear soft preferences."""
    intent = RecommendationIntent.model_validate(raw).model_copy(deep=True)
    for section in ('required', 'preferred'):
        values = getattr(intent, section).categories
        removed = {v for v in values if v.casefold() in GENERIC_CATEGORIES}
        getattr(intent, section).categories = [v for v in values if v not in removed]
        intent.evidence = [e for e in intent.evidence
                           if not (e.field == section + '.categories' and e.value in removed)]
    intent = validate_recommendation_intent(intent, message, history, memory, branch_rules=False)
    selected_tool = tool or ('recommend_bundle' if intent.required.price_basis == 'total' else 'recommend_products')
    intent = validate_recommendation_branch(intent, tool=selected_tool, limit=limit)
    allowed_missing = {'category', 'details'}
    hard = intent.required
    if (set(intent.missing_fields) <= allowed_missing and hard.budget_min is None and hard.budget_max is None
            and hard.price_basis != 'total' and hard.price_min is None
            and hard.price_max is None and not re.search(r'不超过|预算|以内|\d.*(?:美元|元|usd)', request, re.I)):
        intent.missing_fields = []
        intent.action = 'SEARCH'
    if intent.action != 'CLARIFY' and intent.required.categories:
        if data_access is None:
            raise RuntimeError('MCP data access is required')
        if not data_access.call('validate_categories', categories=intent.required.categories)['data']['valid']:
            intent.action = 'CLARIFY'
            intent.missing_fields = ['category']
    if any(v.casefold() in GENERIC_CATEGORIES for v in intent.excluded.categories):
        intent.action = 'CLARIFY'
        intent.missing_fields = ['details']
    # Public uncertainty comes from an actual unmet requirement or tool result,
    # not a stock disclaimer about a broad shopping occasion.
    return intent, []


def create_tool_handlers(model, knowledge_search, message, resolved_question, history, memory, order_context=None,
                         knowledge_context_chars=12000, scoped_knowledge_search=None, knowledge_notes=None,
                         order_query_context=None, *, data_access=None):
    """All arguments supplied by the authenticated application, never from model tool names."""
    if data_access is None:
        raise RuntimeError('MCP data access is required')
    knowledge_search, scoped_knowledge_search, knowledge_notes = data_access.search, data_access.scoped_search, data_access.notes
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
             'evidence.field仅允许required.categories/brands/keywords/price_min/price_max/currency/price_basis/'
             'budget_min/budget_max/budget_mode/quantity_per_product/distinct_count、'
             'preferred.categories/brands/keywords、excluded.categories/brands/keywords。'
             '每个数组元素独立给证据，路径必须是required.categories，不能带[0]、.0等索引；'
             '总价搭配明确的每款数量quantity_per_product和款数distinct_count须给证据；'
             'limit、推荐理由、action、missing_fields不得生成evidence。'
             '例如用户说推荐白茶，证据为field=required.categories,value=白茶,source=CURRENT,quote=白茶,source_id=null。'
             '宽泛推荐可以SEARCH，不必先问预算或品类。价格须十进制字符串；基础币种为人民币CNY，'
             '未注明币种时currency留空由程序默认CNY，不编造币种证据或追问币种；'
             '明确外币时原样提取币种和金额，程序换算，禁止模型自行换算汇率。'
             '按不同茶类推荐属于程序负责的分组，不要从助手的介绍中填入六类硬条件；'
             '只有用户原话明确列出的具体分类才可成为required.categories。'
             '每盒/包/份/单价用price_basis=unit及price_min/price_max；'
             '整笔采购/总价/总预算用price_basis=total及budget_min/budget_max，总价200用budget_max=200。'
             '总预算已明确时不要再追问单价还是总价；缺上限填budget_amount。'
             '总价范围100至200用budget_min=100,budget_max=200；恰好200用两者均200。'
             '总价约200默认不超200；不支持自动超支、差异数量、指定保留/替换商品及超过4款，'
             '此类要求填bundle_constraints且不得忽略。每款数量仅显式给出时填quantity_per_product；'
             '总价搭配明确款数用distinct_count，未指定时程序自动选1至4款；不明预算类型用budget_scope。'
             '总价推荐未指定件数时quantity_policy=automatic，由程序配量，不标purchase_quantity或追问授权；'
             'automatic为程序默认策略，不需要伪造用户授权证据；仅明确拒绝自动配量且未给件数才澄清；'
             '明确每款件数填user_specified；composition仅明确单款或多款时填single或multiple并给证据，套餐本身不代表款数。'
             '左右/接近用budget_mode=near，恰好用exact，明确上限可用cap，并提供对应原话证据。'
             '普通推荐的返回数量由计划limit决定，“推荐一款”不得写入distinct_count或quantity_per_product，'
             '这些购买数量字段和bundle_constraints仅在已识别总价组合时适用。'
             '口感功效认证等无属性证据时标unsupported_attribute，不编造。'
             '日常饮用、每天喝、daily drinking等只是宽泛用途，不填硬属性或unsupported_attribute，'
             '可按已确认茶类搜索，不虚构适用性，不附加商品属性不足等内部校验结论。'
             '用户明确要求认证、成分、含量或功效时，不得因同时提到日常饮用而忽略这些要求；'
             '缺少相应证据仍标unsupported_attribute。'),
            ('human', '购买子任务：{request}\n本轮原话：{message}\n指代补全（不作为原文证据）：{resolved}\n安全历史：{history}\n长期偏好：{memory}\n契约修正要求：{repair}'),
        ])
        options = step.recommendation
        if linked_scope is not None:
            options = options.model_copy(update={'mode': 'by_category'})
        if step.tool == 'recommend_products' and options and options.clarification:
            return result(step, 'needs_clarification', {'answer': options.clarification,
                          'recommendations': [], 'recommendation_status': 'CLARIFY'})
        condition_limit = (options.per_category_limit if options and options.mode == 'by_category' else step.limit)
        topic = purchase_topic(message, step.request, history) if step.purchase_intent is None and linked_scope is None and not (
            options and options.mode == 'by_category') else {'state': 'none'}
        if topic['state'] == 'multiple':
            return result(step, 'needs_clarification', {
                'answer': '刚才涉及{}，您希望推荐哪一类，还是这些茶类都推荐？'.format('、'.join(topic['categories'])),
                'recommendations': [], 'recommendation_status': 'CLARIFY'})
        diagnostics, extraction_attempts, extraction_source = [], 0, 'rules'
        try:
            raw = step.purchase_intent
            if raw is None:
                raw = simple_grouped_intent(message, step.request, history, memory) if options and options.mode == 'by_category' else None
            raw = raw if raw is not None else simple_purchase_intent(message, step.request, history, memory)
            extraction_source = 'semantic_plan' if step.purchase_intent is not None else ('rules' if raw is not None else 'model')
            if raw is not None:
                if step.purchase_intent is not None and memory:
                    # The current authenticated preference record remains the
                    # source of soft preferences, including on the rules path.
                    from .contracts import IntentEvidence
                    raw = raw.model_copy(deep=True)
                    for field in ('categories', 'brands', 'keywords'):
                        values = list(memory['preferences'].get(field, []))
                        setattr(raw.preferred, field, values)
                        raw.evidence = [e for e in raw.evidence if e.field != 'preferred.' + field]
                        raw.evidence.extend(IntentEvidence(field='preferred.' + field, value=value,
                            source='MEMORY', source_id=memory['id'], quote=value) for value in values)
                intent, unmet = normalize_recommendation(apply_purchase_topic(raw, topic), message, history, memory,
                                                       step.request, tool=step.tool, limit=condition_limit, data_access=data_access)
            else:
                for attempt in range(2):
                    extraction_attempts += 1
                    try:
                        raw = (prompt | model.with_structured_output(RecommendationIntent)).invoke(
                            {'request': step.request, 'message': message, 'history': history_json,
                             'resolved': resolved_question, 'memory': json.dumps(memory, ensure_ascii=False),
                             'repair': json.dumps(diagnostics[-1], ensure_ascii=False) if diagnostics else '无；首次提取'})
                        raw = RecommendationIntent.model_validate(raw)
                        intent, unmet = normalize_recommendation(apply_purchase_topic(raw, topic), message, history, memory,
                                                               step.request, tool=step.tool, limit=condition_limit, data_access=data_access)
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
        if intent.required.price_basis == 'total':
            if step.tool != 'recommend_bundle':
                raise ValueError('Total budget requires a server-owned bundle plan')
            scope = linked_scope
            if scope is None and options and options.mode == 'by_category' and options.category_scope == 'basic_tea_types':
                scope = [c for c in BASIC_TEA_TYPES if c not in intent.excluded.categories]
            unsupported_bundle = (
                re.search(r'(?:每类|每种|各类|各)\s*(?:推荐|选|买)?\s*[一二两三四\d]+\s*款', step.request)
                or re.search(r'第[一二两三四\d]+款|(?:这款|那款|商品).{0,12}(?:替换|换掉|换成|保留)|'
                             r'(?:替换|换掉|保留).{0,12}(?:这款|那款|商品|方案)|'
                             r'(?<!不)(?:允许|可以|能)超|上下浮动', step.request)
            )
            if unsupported_bundle:
                intent.action = 'CLARIFY'
                intent.missing_fields = list(dict.fromkeys(intent.missing_fields + ['bundle_constraints']))
            data = data_access.call('recommend_bundle', intent=intent, category_scope=scope, limit=condition_limit)['data']
            if data.get('bundle_missing_fields'):
                intent.missing_fields = list(dict.fromkeys(intent.missing_fields + data['bundle_missing_fields']))
                intent.action = 'CLARIFY'
        elif step.tool == 'recommend_bundle':
            raise ValueError('Total budget tool received unit-price conditions')
        else:
            data = data_access.call('search_products', intent=intent, options=options,
                                    category_scope=linked_scope, limit=step.limit)['data']
        unmet += data.get('unmet_requirements', [])
        if getattr(data_access, 'preference_unavailable', False):
            unmet.append('本次推荐未使用已保存的偏好。')
        data['product_intent'] = intent.model_dump()
        data['condition_source'] = extraction_source
        data['extraction_attempts'] = extraction_attempts
        data['diagnostics'] = data.get('diagnostics', []) + diagnostics
        data['topic_inheritance'] = topic.get('evidence') if topic['state'] == 'single' else None
        data['recommendation_options'] = options.model_dump() if options else None
        data['memory_used'] = any(e.source == 'MEMORY' and e.value in getattr(intent.preferred, e.field.split('.')[-1], [])
                                  for e in intent.evidence)
        data['selected_product'] = data['recommendations'][0] if len(data['recommendations']) == 1 else None
        if data['recommendations'] and intent.required.price_basis != 'total' and REASON_PATTERN.search(step.request):
            data['answer'] = format_product_reasons(data['recommendations'], intent.model_dump(),
                                                  heading='以下是本次推荐及依据（人民币 CNY 单价，价格及库存以下单时为准）：')
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
        notes = knowledge_notes() if knowledge_notes else []
        data, sources = generate_grounded_answer(model, query, evidence, knowledge_context_chars)
        data.update(question=query, evidence_limitations=notes)
        return result(step, 'success' if data['grounding']['claims'] else 'no_match', data, sources=sources, unmet=notes)

    def product_details(step, completed):
        source = completed[step.product_from].data if step.product_from else next(
            (t for t in reversed(history) if (t['turn_id'] == step.reference_turn_id if step.reference_turn_id
             else t.get('product_references') or t.get('recommendation_groups') or t.get('recommendation_bundles'))), {})
        try:
            selected = bundle_products(source, step.request, step.reference_bundle_position)
        except ValueError as exc:
            return result(step, 'needs_clarification', {'answer': str(exc)})
        if step.reference_position is not None:
            selected = selected[step.reference_position - 1:step.reference_position]
        group_match = re.search(r'第' + ORDINAL + r'类', step.request) if step.reference_position is None else None
        index_match = re.search(r'第' + ORDINAL + r'款', step.request) if step.reference_position is None else None
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
        if not step.product_from and not (type(selected[0].get('sku_id')) is int and selected[0]['sku_id'] > 0):
            # Historical names identify an object, never its live price/stock.
            identity = data_access.call('resolve_product', name=selected[0]['name'],
                                        product_name=selected[0]['product_name'])['data']['sku_id']
            if identity is None:
                return result(step, 'needs_clarification', {'answer': '该名称无法唯一定位商品，请重新推荐或明确商品名称。'})
            selected = [{'sku_id': identity}]
        details = data_access.call('get_product_details', sku_id=selected[0]['sku_id'])
        if details['status'] == 'no_match':
            return result(step, 'no_match', {'answer': '所指商品当前未上架或没有可用库存，请重新选择。'})
        return result(step, data=dict(details['data'], observed_at=details['observed_at'], limitations=details['limitations']),
                      unmet=[] if details['data']['attributes'] else [MISSING_ATTRIBUTES])

    def orders(step, completed):
        if step.request not in message:
            return result(step, 'needs_clarification', {'answer': '请在本轮明确要查询的订单和状态。'})
        if '[无效订单引用]' in message:
            return result(step, 'needs_clarification', {'answer': '订单引用已失效，请重新提供真实订单号。'})
        anchors = explicit_requests(message)
        anchor = next((r for r in anchors if r.kind == 'after_sales'), None)
        request = message
        # Preserve constraints outside a model's short quote. Remove only
        # independently recognized other tasks, never overlapping order text.
        for other in anchors:
            if (other.kind != 'after_sales' and step.request not in other.quote
                    and (anchor is None or anchor.quote not in other.quote)):
                request = request.replace(other.quote, ' ', 1)
        # Legacy order_context strings are deliberately not used as live facts.
        if order_query_context is None or order_query_context.owner_id is None:
            return result(step, 'needs_clarification', {'answer': '请先绑定并登录买家账号后查询本人订单。'})
        queried = data_access.call('get_order_status', query=step.order_query or rule_order_query(request), request=request)
        if queried['status'] == 'no_match' and order_query_context.not_queryable:
            return result(step, 'error', dict(queried['data'], error_code='ORDER_NOT_QUERYABLE'))
        return result(step, queried['status'], queried['data'])

    def explain_recommendations(step, completed):
        queried = data_access.call('explain_recommendations', step=step, completed=completed)
        return result(step, queried['status'], queried['data'])

    def clarify(step, completed):
        return result(step, 'needs_clarification', {'answer': '您希望了解茶叶知识、挑选商品，还是查询订单？请补充具体对象或要求。'})

    return {'recommend_products': recommend, 'recommend_bundle': recommend,
            'explain_recommendations': explain_recommendations, 'introduce_tea': introduce,
            'get_product_details': product_details, 'get_order_status': orders, 'ask_clarification': clarify}
