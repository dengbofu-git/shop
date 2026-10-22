"""Bounded, deterministic bundle search. No ORM, model calls or floating money."""
from bisect import insort
from dataclasses import dataclass
from time import monotonic


MAX_CANDIDATES = 40
MAX_NODES = 120000
MAX_SECONDS = 2.0
POOL_SIZE = 64


@dataclass(frozen=True)
class Candidate:
    sku_id: int
    product_id: int
    category: str
    price_cents: int
    available_quantity: int
    preference_score: int = 0


def search_bundles(candidates, *, budget_cents, minimum_cents=0, categories=(),
                   quantity=1, distinct_count=None, preference_max=0):
    """Keep the best 64 plans in at most 40 candidates; never relax hard filters."""
    if (type(budget_cents) is not int or budget_cents <= 0
            or type(minimum_cents) is not int or not 0 <= minimum_cents <= budget_cents
            or type(quantity) is not int or not 1 <= quantity <= 100
            or (distinct_count is not None and (type(distinct_count) is not int or not 1 <= distinct_count <= 4))
            or len(candidates) > MAX_CANDIDATES):
        raise ValueError('Invalid bundle search bounds')
    if len({c.sku_id for c in candidates}) != len(candidates):
        raise ValueError('Duplicate bundle candidate')
    if any(type(value) is not int for c in candidates for value in (
            c.sku_id, c.product_id, c.price_cents, c.available_quantity, c.preference_score)):
        raise ValueError('Bundle candidate money and quantities must be integers')
    required = frozenset(categories)
    low_count = distinct_count if distinct_count is not None else 2
    high_count = distinct_count if distinct_count is not None else 4
    near_floor = max(minimum_cents, (budget_cents * 95 + 99) // 100)
    items = sorted((c for c in candidates if c.price_cents > 0
                    and c.available_quantity >= quantity
                    and c.price_cents * quantity <= budget_cents),
                   key=lambda c: (c.price_cents, c.sku_id))
    suffix_categories = [frozenset() for _ in range(len(items) + 1)]
    for i in range(len(items) - 1, -1, -1):
        suffix_categories[i] = suffix_categories[i + 1] | {items[i].category}
    pool = []
    nodes, valid = 0, 0
    stopped = False
    started = monotonic()

    def visit(start, selected, product_ids, covered, total):
        nonlocal nodes, valid, stopped
        if stopped:
            return
        nodes += 1
        if nodes > MAX_NODES or (nodes % 256 == 0 and monotonic() - started >= MAX_SECONDS):
            stopped = True
            return
        count = len(selected)
        if count >= low_count and total >= minimum_cents and required <= covered:
            valid += 1
            preference = (sum(c.preference_score for c in selected) * 100 // (preference_max * count)
                          if preference_max else 100)
            diversity = len(covered) * 100 // count
            quality = (80 * preference + 20 * diversity) // 100
            ids = tuple(sorted(c.sku_id for c in selected))
            rank = (0 if total >= near_floor else 1, -quality, budget_cents - total, ids)
            if len(pool) < POOL_SIZE or rank < pool[-1][0]:
                insort(pool, (rank, ids, total, quality))
                if len(pool) > POOL_SIZE:
                    pool.pop()
        missing = required - covered
        if (count == high_count or len(missing) > high_count - count
                or not missing <= suffix_categories[start]
                or count + len(items) - start < low_count):
            return
        for i in range(start, len(items)):
            candidate = items[i]
            new_total = total + candidate.price_cents * quantity
            if new_total > budget_cents:
                break  # Ascending prices make this pruning safe.
            if candidate.product_id in product_ids:
                continue
            visit(i + 1, selected + (candidate,), product_ids | {candidate.product_id},
                  covered | {candidate.category}, new_total)
            if stopped:
                break

    visit(0, (), frozenset(), frozenset(), 0)
    return {
        'plans': [{'sku_ids': list(ids), 'subtotal_cents': total, 'quality_score': quality,
                   'near_budget': total >= near_floor} for _, ids, total, quality in pool],
        'nodes': nodes, 'valid_combinations': valid, 'search_complete': not stopped,
        'candidate_count': len(items), 'near_floor_cents': near_floor,
    }
