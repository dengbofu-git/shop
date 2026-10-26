"""Keep server-owned facts as immutable answer units across model review."""
from .pii import redact


BUSINESS_TOOLS = frozenset({'recommend_products', 'recommend_bundle', 'get_product_details',
                            'get_order_status', 'explain_recommendations'})


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
