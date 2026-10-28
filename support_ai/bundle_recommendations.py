"""Read-only total-budget tool: real candidates, bounded search and final recheck."""
from decimal import Decimal
from hashlib import sha256

from .budget_combinations import Candidate, MAX_CANDIDATES
from .bundle_optimizer import optimize_bundles as search_bundles
from .contracts import canonicalize_total_budget, validate_recommendation_branch
from .pii import redact
from .recommendations import CATEGORY_ALIASES, CLARIFICATIONS, product_cards, ranked_products
from .recommendation_presentation import shopping_reasons, bundle_summary
from tea_saas.currency import BASE_CURRENCY, currency, to_base, display, RATES


def cents(value):
    return int(Decimal(value) * 100)


def money(value):
    return format(Decimal(value) / 100, '.2f')


def _candidate(item):
    return Candidate(item.pk, item.spu_id, item.spu.catalog.name, cents(item.price),
                     item.available_stock, item.preference_score)


def _candidates(query, budget_cents, quantity, required_categories):
    """Round-robin across categories and price bands rather than only top sellers."""
    names = required_categories or list(query.order_by('spu__catalog__name').values_list(
        'spu__catalog__name', flat=True).distinct()[:13])
    category_limited = len(names) > 12
    names = names[:12]
    buckets, truncated = [], category_limited
    bucket_limit = min(MAX_CANDIDATES, max(4, MAX_CANDIDATES // max(len(names), 1) + 2))
    # Bands apply to CNY line cost, including the explicit quantity.
    edges = [0, budget_cents // 4, budget_cents // 2, budget_cents]
    for name in names:
        for low, high in zip(edges, edges[1:]):
            bucket = query.filter(spu__catalog__name=name, price__gt=Decimal(low) / (100 * quantity),
                                  price__lte=Decimal(high) / (100 * quantity))
            rows = list(bucket[:bucket_limit + 1])
            truncated |= len(rows) > bucket_limit
            buckets.append(rows[:bucket_limit])
    selected = []
    seen = set()
    for index in range(bucket_limit):
        for bucket in buckets:
            if index < len(bucket) and bucket[index].pk not in seen:
                if len(selected) == MAX_CANDIDATES:
                    truncated = True
                    continue
                selected.append(bucket[index])
                seen.add(bucket[index].pk)
    return selected, truncated


def recommend_bundle(intent, *, category_scope=None):
    """Called only after the application has validated intent provenance."""
    intent = validate_recommendation_branch(canonicalize_total_budget(intent), tool='recommend_bundle')
    empty = {'recommendations': [], 'recommendation_bundles': []}

    def clarify(field):
        return dict(empty, recommendation_status='CLARIFY', answer=CLARIFICATIONS[field],
                    bundle_missing_fields=[field])

    if intent.action == 'CLARIFY':
        return dict(empty, recommendation_status='CLARIFY', bundle_missing_fields=intent.missing_fields,
                    answer=' '.join(CLARIFICATIONS['bundle_quantity' if f == 'purchase_quantity' else f]
                                    for f in intent.missing_fields))
    hard = intent.required
    if hard.price_basis != 'total':
        raise ValueError('recommend_bundle requires a total budget')
    if hard.currency is not None and hard.currency not in RATES:
        return clarify('currency')
    if hard.budget_max is None or cents(hard.budget_max) <= 0:
        return clarify('budget_amount')
    canonical = lambda v: CATEGORY_ALIASES.get(v.casefold(), v)
    categories = list(dict.fromkeys(canonical(v) for v in hard.categories))
    if category_scope is not None:
        scope = list(dict.fromkeys(canonical(v) for v in category_scope))
        categories = [c for c in scope if not categories or c in categories]
        if not categories:
            return dict(empty, recommendation_status='NO_MATCH', answer='茶类说明范围与购买条件没有交集，暂无法搭配。')
    count = 1 if hard.composition == 'single' else hard.distinct_count
    if len(categories) > (count or 4):
        return clarify('bundle_constraints')
    requested_currency = currency(hard.currency)
    budget = cents(to_base(hard.budget_max, requested_currency))
    minimum_value = hard.budget_max if hard.budget_mode == 'exact' else (hard.budget_min or '0')
    minimum = cents(to_base(minimum_value, requested_currency, upper=False))
    if minimum > budget:
        return dict(empty, recommendation_status='NO_MATCH', answer='该外币金额按参考比例换算后无法用人民币分精确满足，请调整预算范围。')
    quantity = hard.quantity_per_product
    minimum_quantity = quantity if quantity is not None else 1
    scoped = intent.model_copy(deep=True)
    scoped.required.categories = categories
    query = ranked_products(scoped, unit_prices=False).filter(
        price__gt=0, price__lte=Decimal(budget) / (100 * minimum_quantity), available_stock__gte=minimum_quantity)
    selected, truncated = _candidates(query, budget, minimum_quantity, categories)
    preference_max = (3 * bool(intent.preferred.categories) + 3 * bool(intent.preferred.brands)
                      + len(intent.preferred.keywords))

    def search(rows):
        return search_bundles([_candidate(p) for p in rows], budget_cents=budget, minimum_cents=minimum,
                              categories=categories, quantity=quantity, distinct_count=count,
                              minimum_distinct=2 if hard.composition == 'multiple' else 1,
                              preference_max=preference_max, prefer_near=hard.budget_mode in ('near', 'exact'))

    searched = search(selected)
    # Requery all candidates once. Search again if prices, availability, categories
    # or preference facts changed. Never return a plan checked against old prices.
    live = list(query.filter(pk__in=[p.pk for p in selected])) if selected else []
    refreshed = {_candidate(p).sku_id: _candidate(p) for p in live}
    changed = refreshed != {p.pk: _candidate(p) for p in selected}
    if changed:
        searched = search(live)
    live_by_id = {p.pk: p for p in live}
    metadata = {k: v for k, v in searched.items() if k != 'plans'}
    metadata.update(candidate_limit=MAX_CANDIDATES, candidates_truncated=truncated,
                    prices_rechecked=True, candidates_changed=changed, globally_optimal=False)
    base = dict(empty, bundle_search=metadata,
                bundle_budget={'currency': BASE_CURRENCY, 'maximum': money(budget), 'minimum': money(minimum),
                               'near_minimum': money(searched['near_floor_cents']), 'allow_over_budget': False,
                               'requested_currency': requested_currency, 'requested_maximum': hard.budget_max,
                               'conversion_kind': 'reference' if requested_currency != BASE_CURRENCY else 'none'},
                bundle_assumptions={'quantity_per_product': quantity, 'quantity_mode': 'fixed' if quantity is not None else 'automatic',
                                    'automatic_quantity_cap': None, 'quantity_bound': 'budget_and_available_stock',
                                    'min_distinct_products': count or (2 if hard.composition == 'multiple' else 1),
                                    'max_distinct_products': count or 4, 'shipping_and_tax_included': False})
    bundles = []
    seen_combinations = set()
    for plan in searched['plans']:
        rows = [live_by_id[pk] for pk in plan['sku_ids']]
        quantities = dict(zip(plan['sku_ids'], plan['quantities']))
        combination = frozenset((p.spu_id, quantities[p.pk]) for p in rows)
        if combination in seen_combinations:
            continue
        # A quantity change is meaningful; merely changing a pack is not.
        seen_combinations.add(combination)
        cards = product_cards(rows, scoped)
        subtotal = sum(cents(c['price']) * quantities[c['sku_id']] for c in cards)
        if not minimum <= subtotal <= budget or any(c['available_stock'] < quantities[c['sku_id']] for c in cards):
            continue
        for card in cards:
            units = quantities[card['sku_id']]
            card.update(quantity=units, line_subtotal=money(cents(card['price']) * units))
            card['reasons'] = shopping_reasons(card)
        signature = '|'.join('{}:{}:{}'.format(c['sku_id'], c['quantity'], c['price']) for c in cards)
        bundle_id = 'bundle-' + sha256((str(budget) + '|' + signature).encode()).hexdigest()[:12]
        bundles.append({'bundle_id': bundle_id, 'position': len(bundles) + 1, 'items': cards,
                        'subtotal': money(subtotal), 'remaining_budget': money(budget - subtotal),
                        'currency': BASE_CURRENCY, 'within_budget': True, 'near_budget': plan['near_budget'],
                        'display_currency': requested_currency,
                        'display_subtotal': format(display(Decimal(subtotal) / 100, requested_currency), '.2f'),
                        'quality_score': plan['quality_score'],
                        'solver_status': plan.get('solver_status'),
                        'objective_value': plan.get('objective_value'),
                        'best_objective_bound': plan.get('best_objective_bound')})
        bundles[-1]['summary'] = bundle_summary(bundles[-1], money(budget), automatic=quantity is None)
        if len(bundles) == 3:
            break
    if not bundles and searched.get('termination_status') == 'UNKNOWN':
        return dict(base, recommendation_status='ERROR',
                    answer='套餐计算在本次时限内尚未找到可验证方案，请稍后重试或缩小条件。')
    if not bundles:
        return dict(base, recommendation_status='NO_MATCH',
                    answer='在当前候选范围内，未找到同时满足总预算、茶类覆盖和商品数量的搭配。'
                           '我没有放宽条件；您可以调整预算、茶类或款数。')
    notice = '商品合计不含运费、税费，价格及可购买状态以下单校验为准。'
    lines = [bundles[0]['summary']]
    if len(bundles) > 1:
        lines.append('另外还有{}套搭配，可在下方切换比较商品和数量。'.format(len(bundles) - 1))
    if requested_currency != BASE_CURRENCY:
        notice += '外币按参考比例显示，实际扣款以支付渠道为准。'
    if any('虚拟' in c['product_name'] or '模拟' in c['product_name']
           or any('模拟' in key for key in c.get('facts', {})) for b in bundles for c in b['items']):
        notice += '含演示商品，模拟属性仅供展示。'
    lines.append(notice)
    return dict(base, recommendation_status='MATCHED', recommendation_bundles=bundles,
                primary_bundle_id=bundles[0]['bundle_id'], bundle_notice=notice, presentation_version='bundles-v2',
                recommendations=bundles[0]['items'], answer=redact('\n'.join(lines)))
