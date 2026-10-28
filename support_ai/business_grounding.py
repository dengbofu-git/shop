"""Keep server-owned facts as immutable answer units across model review."""
from .pii import redact


BUSINESS_TOOLS = frozenset({'recommend_products', 'recommend_bundle', 'get_product_details',
                            'get_order_status', 'explain_recommendations'})


def _fixed_insufficient_text(data):
    from .grounding import INSUFFICIENT
    from .recommendation_options import BASIC_TEA_TYPES
    answer = data.get('answer', '')
    if answer in (INSUFFICIENT, '本次未检索到足够证据说明这些茶类的区别，因此暂不推荐对应商品。'):
        return True
    categories = data.get('unexplained_categories', [])
    if (not isinstance(categories, list) or not 1 <= len(categories) <= 6 or
            any(c not in BASIC_TEA_TYPES for c in categories)):
        return False
    expected = ['茶种一词可能指茶树品种；这里按制造工艺区分的茶类说明：']
    expected.extend('\n{}：本次证据不足，暂不作具体说明，也不据此推荐商品。'.format(c) for c in categories)
    return answer == '\n'.join(expected)


def needs_model_review(results):
    """Only server-owned units and independently grounded knowledge bypass review.

    These flags come from registered handlers, never documents or request JSON.
    Unknown/unverified prose still takes the fail-closed compliance path.
    """
    fixed_tools = {'greet_user', 'describe_capabilities', 'ask_clarification'}
    for result in results:
        tool, data = result['tool'], result['data']
        if tool in BUSINESS_TOOLS or tool in fixed_tools:
            continue
        if tool == 'introduce_tea':
            grounding = data.get('grounding', {})
            claims = grounding.get('claims', [])
            # A bare status string is not sufficient provenance. Require the
            # server's accepted units and source map to match rendered text.
            if (grounding.get('status') in ('verified', 'partial') and claims and
                    grounding.get('sources') and all(isinstance(c, dict) and
                        isinstance(c.get('text'), str) and c['text'] and
                        c['text'] in data.get('answer', '') and c.get('citations') for c in claims)):
                continue
            if (grounding.get('status') == 'insufficient' and not claims and
                    not grounding.get('sources') and not result.get('sources') and _fixed_insufficient_text(data)):
                continue
            if result['status'] in ('error', 'skipped') and data.get('answer') in (
                    '该项服务暂时不可用，请稍后重试。',
                    '本次模型处理已达到预算，暂未完成该项，请稍后单独查询。',
                    '前置任务未取得有效结果，暂无法继续该项查询。',
                    '本次处理已达到时间预算，请稍后继续。'):
                continue
        return True
    return False


def render_product_details(data):
    """Public DTO fields, never an LLM paraphrase of price/currency/stock."""
    lines = ['{} · {}'.format(data['product_name'], data['specification']),
             '分类：{}。'.format(data['category']),
             '单价：{} {}。可用库存：{}件。'.format(data['price'], data['currency'], data['available_stock'])]
    for row in data.get('attributes', []):
        value = next((row.get(key) for key in ('value_text', 'value_number', 'value_boolean', 'value_date')
                      if row.get(key) is not None and row.get(key) != ''), None)
        if value is not None:
            lines.append('{}：{}。'.format(row['attribute__name'], value))
    if not data.get('attributes'):
        lines.append('该商品未配置可验证的风味、用途等公开结构化属性。')
    if data.get('observed_at'):
        lines.append('查询时间：{}。'.format(data['observed_at']))
    lines.append('价格及库存为本次查询结果，不锁价、不预留，以下单校验为准。')
    return redact('\n'.join(lines))


def make_answer_block(result):
    data = result['data']
    if result['tool'] == 'get_product_details' and result['status'] == 'success':
        text = render_product_details(data)
    else:
        # Other business answers are computed by the registered Python handlers.
        # Missing text is never filled by inventing facts through a composer.
        text = data.get('answer') or '该项暂时没有可验证的回答，请稍后重试。'
    return {'step_id': result['step_id'], 'business': result['tool'] in BUSINESS_TOOLS,
            'text': redact(text)}


def enforce_answer_consistency(candidate, blocks):
    """Exact unit preservation also rejects swapped objects and new promises.

    Checking only a bag of numbers would accept 99 CNY -> 99 USD or exchanging
    two products' prices. Reject the entire rewrite and render intact units.
    """
    expected = '\n\n'.join(block['text'] for block in blocks)
    return expected, {'status': 'preserved' if any(b['business'] for b in blocks) else 'not_applicable',
                      'protected_steps': [b['step_id'] for b in blocks if b['business']],
                      'rewrite_rejected': candidate != expected}
