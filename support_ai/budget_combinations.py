"""Legacy beam baseline for comparison; production uses bundle_optimizer CP-SAT."""
from dataclasses import dataclass
from math import gcd
from time import monotonic


MAX_CANDIDATES = 40
MAX_NODES = 120000
MAX_SECONDS = 2.0
POOL_SIZE = 64
BEAM_WIDTH = 96
QUANTITY_OPTION_LIMIT = 64
PAIR_TARGET_LIMIT = 16


def _bounded_pair(first, second, target):
    """Solve p*x+q*y=target inside both stock bounds, without enumerating units."""
    common = gcd(first.price_cents, second.price_cents)
    if target % common:
        return None
    a, b, total = first.price_cents // common, second.price_cents // common, target // common
    x0 = (total * pow(a, -1, b)) % b if b > 1 else 0
    y0 = (target - first.price_cents * x0) // second.price_cents
    ceil_div = lambda x, y: -((-x) // y)
    low = max(ceil_div(1 - x0, b), ceil_div(y0 - second.available_quantity, a))
    high = min((first.available_quantity - x0) // b, (y0 - 1) // a)
    if low > high:
        return None
    step = high if b < a else low
    return x0 + b * step, y0 - a * step


@dataclass(frozen=True)
class Candidate:
    sku_id: int
    product_id: int
    category: str
    price_cents: int
    available_quantity: int
    preference_score: int = 0


def search_bundles(candidates, *, budget_cents, minimum_cents=0, categories=(),
                   quantity=None, distinct_count=None, preference_max=0, prefer_near=False, minimum_distinct=1):
    """Bounded beam search over product AND quantity; all amounts are cents."""
    if type(minimum_distinct) is not int or not 1 <= minimum_distinct <= 4:
        raise ValueError('Invalid minimum distinct count')
    if (type(budget_cents) is not int or budget_cents <= 0
            or type(minimum_cents) is not int or not 0 <= minimum_cents <= budget_cents
            or (quantity is not None and (type(quantity) is not int or not 1 <= quantity <= 100))
            or (distinct_count is not None and (type(distinct_count) is not int or not 1 <= distinct_count <= 4))
            or len(candidates) > MAX_CANDIDATES):
        raise ValueError('Invalid bundle search bounds')
    if len({c.sku_id for c in candidates}) != len(candidates):
        raise ValueError('Duplicate bundle candidate')
    if any(type(value) is not int for c in candidates for value in (
            c.sku_id, c.product_id, c.price_cents, c.available_quantity, c.preference_score)):
        raise ValueError('Bundle candidate money and quantities must be integers')
    required = frozenset(categories)
    low_count = distinct_count if distinct_count is not None else minimum_distinct
    high_count = distinct_count if distinct_count is not None else 4
    near_floor = max(minimum_cents, (budget_cents * 95 + 99) // 100)
    minimum_quantity = quantity if quantity is not None else 1
    items = sorted((c for c in candidates if c.price_cents > 0
                    and c.available_quantity >= minimum_quantity
                    and c.price_cents * minimum_quantity <= budget_cents),
                   key=lambda c: (c.price_cents, c.sku_id))
    suffix_categories = [frozenset() for _ in range(len(items) + 1)]
    for i in range(len(items) - 1, -1, -1):
        suffix_categories[i] = suffix_categories[i + 1] | {items[i].category}
    pool = {}
    nodes, valid = 0, 0
    stopped, pruned = False, False
    started = monotonic()
    # State: selected (candidate, quantity) pairs, product IDs, categories, total.
    beams = {0: [((), frozenset(), frozenset(), 0)]}

    def ranking(state):
        selected, _, covered, total = state
        count = len(selected)
        preference = (sum(c.preference_score for c, _ in selected) * 100 // (preference_max * count)
                      if preference_max else 100)
        diversity = len(covered) * 100 // count
        quality = (80 * preference + 20 * diversity) // 100
        signature = tuple(sorted((c.sku_id, q) for c, q in selected))
        # 普通预算优先较少件数，不为消耗预算自动扩大量；明确接近时才优先差额。
        quantity_total = sum(q for _, q in selected)
        tail = ((-quality, budget_cents - total, quantity_total, count, signature) if prefer_near
                else (-quality, quantity_total, count, total, signature))
        return ((0 if total >= near_floor else 1,) + tail if prefer_near else tail), quality, signature

    def retain(states):
        nonlocal pruned
        if len(states) <= BEAM_WIDTH:
            return states
        pruned = True
        buckets = {}
        for state in states:
            key = (tuple(sorted(state[2] & required)), min(7, state[3] * 8 // budget_cents))
            buckets.setdefault(key, []).append(state)
        for values in buckets.values():
            values.sort(key=lambda s: ranking(s)[0])
        keys = sorted(buckets, key=lambda k: (-len(k[0]), -k[1], k[0]))
        kept = []
        for i in range(BEAM_WIDTH):
            for key in keys:
                if i < len(buckets[key]):
                    kept.append(buckets[key][i])
                    if len(kept) == BEAM_WIDTH:
                        return kept
        return kept

    def record(state):
        nonlocal valid
        if (low_count <= len(state[0]) <= high_count and state[3] >= minimum_cents
                and required <= state[2]):
            valid += 1
            rank, quality, signature = ranking(state)
            pool[signature] = (rank, signature, state[3], quality)
            if len(pool) > POOL_SIZE:
                del pool[max(pool, key=lambda key: pool[key][0])]

    # Strong single/pair seeds are found before beam pruning. In particular,
    # preferences do not prevent 75*18 + 66*25 from reaching a 3000 budget.
    if quantity is None:
        for candidate in items:
            units = min(candidate.available_quantity, budget_cents // candidate.price_cents)
            record((((candidate, units),), frozenset({candidate.product_id}),
                    frozenset({candidate.category}), candidate.price_cents * units))
        if low_count <= 2 <= high_count:
            for index, first in enumerate(items):
                for second in items[index + 1:]:
                    if first.product_id == second.product_id or not required <= {first.category, second.category}:
                        continue
                    common = gcd(first.price_cents, second.price_cents)
                    upper = min(budget_cents, first.price_cents * first.available_quantity +
                                second.price_cents * second.available_quantity)
                    upper -= upper % common
                    for offset in range(PAIR_TARGET_LIMIT):
                        target = upper - offset * common
                        nodes += 1
                        if target < minimum_cents or target <= 0:
                            break
                        if nodes > MAX_NODES or (nodes % 128 == 0 and monotonic() - started >= MAX_SECONDS):
                            stopped = True
                            break
                        solution = _bounded_pair(first, second, target)
                        if solution:
                            one, two = solution
                            record((((first, one), (second, two)), frozenset({first.product_id, second.product_id}),
                                    frozenset({first.category, second.category}), target))
                    if stopped:
                        break
                if stopped:
                    break

    for index, candidate in enumerate(items):
        if stopped:
            break
        for count in range(high_count, 0, -1):
            generated = []
            for state in beams.get(count - 1, []):
                selected, product_ids, covered, total = state
                if candidate.product_id in product_ids:
                    continue
                ceiling = min(candidate.available_quantity, (budget_cents - total) // candidate.price_cents)
                choices = [quantity] if quantity is not None and quantity <= ceiling else (
                    range(1, ceiling + 1) if quantity is None else [])
                if quantity is None and ceiling > QUANTITY_OPTION_LIMIT:
                    pruned = True
                    choices = sorted(set(range(1, 9)) | {ceiling - i for i in range(8)} |
                        {1 + (ceiling - 1) * i // 47 for i in range(48)}, reverse=True)
                for units in choices:
                    nodes += 1
                    if nodes > MAX_NODES or (nodes % 128 == 0 and monotonic() - started >= MAX_SECONDS):
                        stopped = True
                        break
                    next_state = (selected + ((candidate, units),), product_ids | {candidate.product_id},
                                  covered | {candidate.category}, total + candidate.price_cents * units)
                    record(next_state)
                    missing = required - next_state[2]
                    if (count < high_count and len(missing) <= high_count - count
                            and missing <= suffix_categories[index + 1]):
                        generated.append(next_state)
                if stopped:
                    break
            beams[count] = retain(beams.get(count, []) + generated)
            if stopped:
                break
        if stopped:
            break
    ordered = sorted(pool.values(), key=lambda row: row[0])
    return {
        'plans': [{'sku_ids': [pk for pk, _ in signature], 'quantities': [q for _, q in signature],
                   'subtotal_cents': total, 'quality_score': quality,
                   'near_budget': total >= near_floor} for _, signature, total, quality in ordered],
        'nodes': nodes, 'valid_combinations': valid, 'search_complete': not stopped and not pruned,
        'candidate_count': len(items), 'near_floor_cents': near_floor,
        'quantity_mode': 'fixed' if quantity is not None else 'automatic',
        'automatic_quantity_cap': None, 'quantity_bound': 'budget_and_available_stock',
        'quantity_option_limit': QUANTITY_OPTION_LIMIT, 'pair_target_limit': PAIR_TARGET_LIMIT,
        'beam_width': BEAM_WIDTH,
    }
