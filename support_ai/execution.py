"""Bounded executor: tools never control the next step or return executable code."""
import time
from typing import Literal

from pydantic import BaseModel, Field

from .planning import TaskPlan, validate_plan
from .diagnostics import error_diagnostic
from .telemetry import agent_span
from .cost_control import ModelBudgetExceeded


class ToolResult(BaseModel):
    step_id: str
    tool: str
    status: Literal['success', 'no_match', 'needs_clarification', 'error', 'skipped']
    data: dict = Field(default_factory=dict)
    sources: list = Field(default_factory=list)
    unmet_requirements: list = Field(default_factory=list)


def execute_plan(plan, handlers, budget_seconds=90):
    plan = TaskPlan.model_validate(plan)
    validate_plan(plan)
    completed = {}
    started = time.monotonic()
    for _ in range(len(plan.steps)):
        ready = next((s for s in plan.steps if s.id not in completed
                      and all(d in completed for d in s.depends_on)), None)
        if ready is None:
            break
        with agent_span('tool.' + ready.tool, {'agent.tool.step': ready.id}) as span:
            if any(completed[d].status != 'success' for d in ready.depends_on):
                result = ToolResult(step_id=ready.id, tool=ready.tool, status='skipped',
                                    data={'answer': '前置任务未取得有效结果，暂无法继续该项查询。'})
            elif time.monotonic() - started >= budget_seconds:
                result = ToolResult(step_id=ready.id, tool=ready.tool, status='error',
                                    data={'answer': '本次处理已达到时间预算，请稍后继续。', 'error_type': 'BudgetExceeded'})
            elif ready.tool not in handlers:
                raise ValueError('Tool is not registered')
            else:
                try:
                    result = ToolResult.model_validate(handlers[ready.tool](ready, completed))
                    if result.step_id != ready.id or result.tool != ready.tool:
                        raise ValueError('Tool result identity mismatch')
                except Exception as exc:
                    if span:
                        span.set_attribute('error.type', type(exc).__name__)
                    result = ToolResult(step_id=ready.id, tool=ready.tool, status='error',
                                        data={'answer': ('本次模型处理已达到预算，暂未完成该项，请稍后单独查询。'
                                                        if isinstance(exc, ModelBudgetExceeded) else '该项服务暂时不可用，请稍后重试。'), 'error_type': type(exc).__name__,
                                              'diagnostics': [error_diagnostic(exc, ready.tool)]})
            completed[ready.id] = result
            if span:
                span.set_attribute('agent.tool.status', result.status)
    return [completed[step_id] for step_id in plan.output_order]
