# 0010 使用CP-SAT计算预算套餐

Status: accepted
Date: 2026-10-28
Decision makers: 用户在检索OR-Tools、SciPy、PuLP的比较后明确要求“实现”。

当前自写beam排序先后出现单款数百件和预算3000元仅推荐7.40元单件的退化。采用OR-Tools CP-SAT求解整数数量与商品选择，由Python定义硬约束及版本化软目标，Agent只理解需求；不扩大MCP数据权限。

给定总预算默认允许自动配量，撤销0.25.x强制数量授权。目标为可审阅的balanced-cpsat-v1，不将求解器可行或最优等同推荐质量；业务目标与真实用户评价仍需持续验证。数量集中采用软惩罚，明确大批量或件数不受任意硬上限影响。保留原先实时事实复验、候选限制及预算上界。

OR-Tools增加原生包及pandas等运行依赖；锁定9.15.6755及解析后的依赖，检查不升级现有NumPy／Protobuf。对比实际公开候选后接入生产工具，旧beam保留仅作基线。可行状态与时限公开到诊断，不承诺全局最优。

依据：[官方CP-SAT](https://developers.google.com/optimization/cp/cp_solver)、[时限](https://developers.google.com/optimization/cp/cp_tasks)、[本项目规格](../sdd/modules/ai-support/total-budget-recommendation.md)。
