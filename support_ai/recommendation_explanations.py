"""Explain a bound recommendation list using current SKU facts, without a new search."""
import re
from .pii import redact
from .recommendations import available_products, product_cards
from .recommendation_options import ORDINAL, number
from .conversation_tasks import tea_mentions
from .bundle_references import bundle_products


from .recommendation_presentation import _basis, format_product_reasons


def explain_existing_products(step, completed, history):
    source = completed[step.product_from].data if step.product_from else next(
        (t for t in reversed(history) if (t['turn_id'] == step.reference_turn_id if step.reference_turn_id
         else t.get('product_references') or t.get('recommendation_groups') or t.get('recommendation_bundles'))), {})
    try:
        references = bundle_products(source, step.request, step.reference_bundle_position)[:12]
    except ValueError as exc:
        return 'needs_clarification', {'answer': str(exc), 'explained_products': [], 'explanation_status': 'needs_clarification'}
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
            matches = list(available_products().filter(name=reference.get('name', ''),
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
