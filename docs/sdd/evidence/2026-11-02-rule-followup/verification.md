# 逐项规则后续处理记录

日期2026-11-02（Asia/Shanghai）。复用`codex/core-sdd-remediation`，HEAD基线`0d53d1423cbeb349730ff9462e5798fb5f58cb59`。本轮开始时上轮修复仍为未提交增量；保留原工作及历史证据，不改历史Migration。此记录对应用户“继续逐项处理，做好记录”。

## 本轮逐项结果

| 项 | 根因及处置 | 验证／剩余边界 |
| --- | --- | --- |
| R03 普通预算匹配优先 | 原balanced-cpsat-v1将偏好与金额利用加权求和，高匹配10元与弱匹配99元在100元预算单款竞争时误选后者。先写失败反例，再改match-first-cpsat-v2分阶段求解：默认匹配→平衡，明确near/exact为金额→匹配→平衡。匹配沿用现有分数，每个所选SPU归一化后取平均，不按购买件数累加；硬需求及预算优先满足 | 12个求解器用例覆盖普通/接近、硬预算下限、多款弱偏好填充、时限回退及小规模穷举。实际合成商品→候选→求解→工具投影也验证两种模式选择正确；无偏好沿用原平衡策略。候选仍最多40，不能声称全库或真实用户质量最优 |
| R08 恢复反馈 | 原loadHistory捕获GET错误不向调用方报告，restoreHiddenHistory无条件覆盖为成功；等待期间账号切换也可能被覆盖。加载函数现在返回成功/失败，恢复后仅同身份且加载成功才提示成功 | 新增网络失败/身份变化反例；先修正测试未等待异步恢复的问题，确认原实现2失败，再修运行代码到7项通过。解除本地隐藏已经成功时不回滚该操作，保留列表GET错误供重试；数据库仍无DELETE |

R03每个阶段使用同一候选、硬约束及总搜索时限；阶段仅FEASIBLE不能声称其优先级已证最优。后续阶段超时可返回之前验证可行解，投影`objective_stage`、`match_score`及各优先阶段是否最优。平衡分数和求解上界必须结合所标阶段阅读。

## 验证命令与结果

Python3.13.18/Django5.2.18，解释器`.scratch/runtime-py313/Scripts/python.exe`；所有目录/数据为本机隔离合成夹具，无真实模型、支付或业务库调用。

- `python -m unittest support_ai.test_bundle_optimizer.CpSatBundleTests.test_default_match_beats_weak_match_near_budget support_ai.test_bundle_optimizer.CpSatBundleTests.test_explicit_near_preserves_amount_priority -v`：修复前2项，普通模式失败、接近模式通过，证明原排序缺陷。日志`.scratch/rules-followup/r03-red.log`。
- `manage.py test support_ai.test_bundle_priority support_ai.test_bundle_optimizer support_ai.test_budget_combinations support_ai.test_budget_quantities support_ai.test_bundle_intent_boundary support_ai.test_total_budget_generic_tea support_ai.test_initial_budget_evidence support_ai.test_colloquial_budget_graph support_ai.test_budget_scope_semantics support_ai.test_task_tools support_ai.test_mcp_data --settings=support_ai.test_settings --noinput`：103项全部通过，无跳过，4.652秒；日志`.scratch/rules-followup/final-recommendation.log`。涵盖求解、硬条件、工具分流、总价多轮、任务与MCP数据边界；不以此替代真实HTTP MCP集成或模型质量验收。
- `node --test client/tests/support-history-restore.test.js`：新增异步反例修复前7项中2失败，修复后7项全部通过。日志`.scratch/rules-followup/r08-red.log`及`r08-green.log`。此前只等待无返回Promise的点击包装器，断言曾早于异步完成，现直接等待实际恢复函数；撤销包装器也返回Promise。
- `node --test <client/tests/*.test.js逐个文件参数>`：107项全部通过，无跳过；日志`.scratch/rules-followup/frontend-final.log`。覆盖既有订单/币种/采购车/看板及客服交互回归，不等于人工浏览器或移动端验收。
- 收尾检查：`tools/module_versions.py check`通过，15模块所有工作区文件有归属；`makemigrations --check --dry-run --settings=support_ai.test_settings`无差异；命名回归4项通过。4份本轮Python AST、2份JavaScript语法、buyer_support模板编译及`git diff --check`通过。没有暂存文件，两个原有Worktree保持，未新增或移除。source-snapshot.json列出本轮17份文件实际SHA256，不覆盖10月30日证据。

## 规则盘点及下一步

| 规则 | 当前状态 | 后续未完成工作 |
| --- | --- | --- |
| R01/R02 | 上轮依赖隔离、部分结果及回放已实现；本轮相关MCP数据和任务定向回归通过 | 完整CAP全部AC及实机状态反馈验收 |
| R03 | 本轮补齐匹配优先，源码及合成回归通过 | 真实推荐质量/候选裁剪评估，运行启用 |
| R04/R07 | 保留此前取消/隐藏分离、库存并发与防占位规则及其原始证据，本轮未改 | 不将旧启用证据冒充本日运行检查；不擅自提高限额 |
| R05 | 上轮新增可空币种快照、未知投影及财务/支付保护，0007隔离MySQL已验证 | 业务库备份/迁移和统一重启未授权执行；真实支付/退款/渠道币种未联调 |
| R06 | 公开缺货详情与可购买集合拆分，保留上轮证据 | 真实浏览器操作及运行启用核验 |
| R08 | 本地移出/撤销/恢复已有，本轮补加载失败与账号变化反馈 | 键盘/移动端实机检查与运行启用 |
| R09 | Redis当前页方案经用户确认、已有私有映射及隔离MySQL/Redis证据 | 本轮未重复组件测试，真实页面与统一运行启用待做；Q-013聊天/日志等保留期仍开放 |
| R10/R11 | 现行规则/源码观察/证据分开登记，不由测试数提升批准或部署状态 | 随后续结果持续更新，不修改原日期证据 |

试单/预售正式业务、资金清结算、租户订阅、国际履约和新增搜索工具仍属未确认业务分支，不从“继续处理”推导具体产品选择。无来源市场数据继续占位。

版本更新为support_ai0.30.1、web0.36.1；其他模块保持上轮版本。未提交、推送、建PR、迁移业务库、重启或部署。当前运行版本不因源码修改自动更新；无本轮临时Worktree或容器需回收。精确源码快照见同目录source-snapshot.json；它只绑定本轮修复与测试文件，不能单凭旧HEAD重现整个脏现场。
