"""Conservative fidelity checks after the planner selects a new purchase task."""
import re
from decimal import Decimal

from .contracts import IntentEvidence, _value_supported
from .total_budget_intent import AMOUNT


def normalize_planned_defaults(purchase, message):
    """所有规划动作统一消除非用户事实的空值标记及默认预算上限。"""
    result = purchase.model_copy(deep=True)
    removable = set()
    hard = result.required
    if hard.budget_mode == 'cap' and not _value_supported('required.budget_mode', 'cap', message):
        proofs = [e for e in result.evidence if e.field == 'required.budget_mode']
        if all(e.source == 'CURRENT' and e.source_id is None and e.context_turn_id is None for e in proofs):
            hard.budget_mode = None
            removable.add('required.budget_mode')
    for field, marker in [('composition', 'unspecified'), ('quantity_policy', 'clarify')]:
        if field == 'quantity_policy' and re.search(r'(?:不要|不允许|禁止|不用|不想).{0,4}(?:自动|配量)', message):
            continue
        if getattr(hard, field) == marker:
            proofs = [e for e in result.evidence if e.field == 'required.' + field]
            if all(e.source == 'CURRENT' and e.source_id is None and e.context_turn_id is None for e in proofs):
                removable.add('required.' + field)
    result.evidence = [e for e in result.evidence if e.field not in removable]
    return result


def reconcile_initial_purchase(purchase, message):
    """Keep explicit money without guessing scope, changing tasks or prior state."""
    result = purchase.model_copy(deep=True)
    hard = result.required
    # Do not normalize away forged or stale ownership evidence. The ordinary
    # provenance validator must still reject it before any query.
    if any(item.source != 'CURRENT' or item.source_id is not None or item.context_turn_id is not None
           for item in result.evidence):
        return result
    # Generic tea is the shop's scope, not a concrete catalog classification.
    hard.categories = [term for term in hard.categories if term not in ('茶', '茶叶')]
    result.evidence = [item for item in result.evidence
                       if not (item.field == 'required.categories' and item.value in ('茶', '茶叶'))]
    # cap is already the default ceiling policy. A model's optional default
    # must not masquerade as an additional explicitly sourced buyer condition.
    if hard.budget_mode == 'cap' and not _value_supported('required.budget_mode', 'cap', message):
        hard.budget_mode = None
        result.evidence = [item for item in result.evidence if item.field != 'required.budget_mode']
    amounts = (hard.price_min, hard.price_max, hard.budget_min, hard.budget_max)
    if any(value is not None for value in amounts):
        return result
    # Only repair an omitted, single positive monetary mention after intent
    # selection, with no other number, comparison, past price or per-item assertion.
    # Other wording remains with the planner; never turn it into a broad query.
    found = list(re.finditer(r'(?<![\d.])(?P<amount>' + AMOUNT + r')\s*(?P<unit>块钱|块|元钱|元)(?!茶饼|茶砖)', message))
    if not found:
        return result
    if (len(found) != 1 or len(re.findall(r'\d+(?:\.\d+)?', message)) != 1
            or re.search(r'以前|原价|之前|上次|退款|不要|不是|高于|低于|超过|至少|以上|以下|以内|至|到|每|单价', message)):
        result.action = 'CLARIFY'
        result.missing_fields = list(dict.fromkeys(result.missing_fields + ['budget_amount']))
        return result
    amount = found[0]
    if Decimal(amount['amount']) <= 0 or hard.currency not in (None, 'CNY'):
        result.action = 'CLARIFY'
        result.missing_fields = list(dict.fromkeys(result.missing_fields + ['budget_amount']))
        return result
    hard.price_max, hard.price_basis = amount['amount'], 'unknown'
    hard.currency = 'CNY'
    result.evidence = [item for item in result.evidence
                       if item.field not in ('required.price_basis', 'required.currency')]
    result.evidence.extend([
        IntentEvidence(field='required.price_max', value=amount['amount'], source='CURRENT', quote=amount['amount']),
        IntentEvidence(field='required.currency', value='CNY', source='CURRENT', quote=amount['unit']),
    ])
    result.action = 'CLARIFY'
    result.missing_fields = list(dict.fromkeys(result.missing_fields + ['budget_scope']))
    return result
