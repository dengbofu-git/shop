# CP-SAT预算套餐实现验证

日期2026-10-28。用户明确授权实现检索后推荐的OR-Tools方案；support_ai 0.26.0、core 0.11.0。保留当前分支其他未提交工作，未提交／推送／创建PR。

## 实现与策略

生产recommend_bundle改用OR-Tools 9.15.6755 CP-SAT；旧beam仅用于基线。预算、整数件数、库存、明确款数／件数、分类覆盖、同SPU互斥仍为硬约束；最多3套不同SPU集合，共享2秒搜索预算，返回前重新检查商品事实。价格变化重算可能增加一次求解时限。UNKNOWN不冒充无匹配，FEASIBLE不冒充已证明最优，均不声称全库最优。

撤销先确认购买件数或再次授权的门槛，总预算默认自动配量；明确拒绝自动配量仍澄清。新请求不误继承历史茶类。采用明确版本的多目标策略，参数及业务解释见[规格](../../modules/ai-support/total-budget-recommendation.md)，没有宣称这些权重是行业标准。

## 实际公开候选对比

只读事务从当前公开可售SKU取得同一40候选，使用相同3000元预算及合成绿茶／白茶软偏好；无用户身份、订单或个人对话。完整候选及原始结果在public-comparison.json。

| 指标 | 旧beam | CP-SAT balanced-cpsat-v1 |
|---|---|---|
| 首选款数／总件数 | 1款／1件 | 4款／52件 |
| 首选合计 | 7.40元 | 2997元 |
| 三套合计 | 7.40／9／9元 | 2997／2996／3000元 |
| 搜索耗时 | 1816.519ms | 2007.211ms |
| 状态 | 启发式裁剪、未证明全局最优 | 三套FEASIBLE，未证明候选最优 |

这是同一商品快照的一次比较，说明修正了这个具体退化，不证明普遍质量提升或更低耗时。质量评分quality_score保留原描述性口径，并非CP-SAT objective_value。目标中的集中度、体量及递减收益是软约束，不能保证所有数据集都产生低件数；仅有廉价SKU时接近预算本就可能需要大量件数。

## 验证

Python3.13.18／Django5.2运行环境，NumPy2.5.4及Protobuf6.33.6保持原版本。uv依赖解析仅新增ortools、absl-py、immutabledict、pandas、python-dateutil、six，精确版本在constraints-py313.txt。

```powershell
& .scratch/runtime-py313/Scripts/python.exe -X utf8 manage.py test support_ai.test_bundle_optimizer support_ai.test_bundle_intent_boundary support_ai.test_semantic_planning support_ai.test_budget_combinations support_ai.test_budget_quantities support_ai.test_total_budget_generic_tea support_ai.test_initial_budget_evidence support_ai.test_colloquial_budget support_ai.test_colloquial_budget_graph support_ai.test_budget_scope_semantics support_ai.test_mcp_data --settings=support_ai.test_settings --verbosity 0
uv --cache-dir .scratch/bundle-cpsat-20261028/uv-cache pip check --python .scratch/runtime-py313/Scripts/python.exe
```

105项通过，系统检查无问题；依赖检查86个包全部兼容。首次预检误用无pip的venv，随后改用现有uv；一次uv默认缓存权限失败后改工作区缓存，不影响依赖一致性。旧数量授权断言按用户本次决定更新。最终日志在本机.scratch/bundle-cpsat-20261028/final-tests.log。

测试包括：真实CP-SAT与小规模整数穷举的目标交叉校验、明确接近模式、预算／库存／同SPU／数量、金额精确匹配、超大件数、不同方案集合、INFEASIBLE与无时限UNKNOWN；默认配量、明确拒绝、原句规划、会话持久化后数量修改、MCP边界；旧beam算法测试仅作基线，不代表新优化器验收。

此外，真实stdio MCP SDK及Django桥接进程已查询公开商品：无用户身份，合成“总预算3000元”，不指定数量，返回success／MATCHED及ortools-cp-sat。三套4款套餐合计3000／2994／3000元，详见native-mcp.json。不是SyntheticMcpTransport，没有调用模型、创建订单或保存聊天。MCP Schema与当前导出内容一致，改动文件git diff --check通过。

## 运行与边界

加载修复使用已登记的本地预览启动器，身份核验后只重启8000端口开发服务。没有迁移数据库、修改历史对话、调整权限或部署容器。没有真实付费模型评测、浏览器认证聊天验收、全项目测试或Docker构建；实时模型语义识别质量和广泛推荐体验未据此宣称通过。
