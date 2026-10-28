"""Repair provenance for one extracted field, never rewrite purchase conditions."""
import json
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from pydantic import Field

from .contracts import Contract, IntentEvidence, IntentEvidenceError, canonicalize_total_budget


class PurchaseEvidenceRepair(Contract):
    evidence: List[IntentEvidence] = Field(default_factory=list, max_length=40)
    unresolved_scope: bool = False


def repair_purchase_evidence(model, purchase, error, message, history, memory):
    if model is None:
        raise error
    prompt = ChatPromptTemplate.from_messages([
        ('system', '只修正指定购买字段的来源证据，不改变任何已提取的条件值、任务或数量。'
         'evidence.field只能使用待修复字段；同一数组字段的每个条件值分别提供证据。'
         'CURRENT.quote必须逐字来自本轮原话；CONTEXT只能引用给定历史用户原话及其turn_id；'
         'MEMORY只用于软偏好，使用给定记忆的ID与值。context_turn_id必须留空。'
         '不要用人民币等规范化词替代原文中的块；证据引用原词块而value保留CNY。'
         'price_basis=unknown表示尚未确定预算口径，不是用户条件，不需要虚构证据。'
         '若待修复字段为required.price_basis且原话不能证明单价或总价，unresolved_scope=true并不给该字段证据。'
         '不能用助手内容、默认值或猜测补证据；无法证明其他字段则返回空evidence，不能删除条件。'),
        ('human', '本轮原话：{message}\n待修复字段：{field}\n错误码：{code}\n当前条件：{purchase}'
         '\n历史用户原话：{history}\n当前记忆：{memory}'),
    ])
    try:
        repaired = (prompt | model.with_structured_output(PurchaseEvidenceRepair)).invoke({
            'message': message, 'field': error.field, 'code': error.code,
            'purchase': json.dumps({key: value for key, value in purchase.model_dump().items() if key != 'evidence'}, ensure_ascii=False),
            'history': json.dumps([{key: turn[key] for key in ('turn_id', 'user_text')} for turn in history], ensure_ascii=False),
            'memory': json.dumps(memory, ensure_ascii=False)})
        repaired = PurchaseEvidenceRepair.model_validate(repaired)
        if any(e.field != error.field or e.context_turn_id is not None for e in repaired.evidence):
            raise ValueError('Repair changed an unrelated provenance field')
        result = purchase.model_copy(deep=True)
        if repaired.unresolved_scope:
            if error.field != 'required.price_basis':
                raise ValueError('Unexpected unresolved scope')
            result.required.price_basis = 'unknown'
            result.missing_fields = list(dict.fromkeys(result.missing_fields + ['budget_scope']))
            result.action = 'CLARIFY'
        result.evidence = [e for e in result.evidence if e.field != error.field] + repaired.evidence
        return canonicalize_total_budget(result)
    except (ValueError, TypeError) as exc:
        raise IntentEvidenceError(error.field, 'repair_rejected', '购买条件证据仍不足，请明确该条件', repairable=False) from exc
