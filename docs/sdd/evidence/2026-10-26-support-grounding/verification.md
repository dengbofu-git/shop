# 买家助手结论证据与业务事实一致性验证

日期：2026-10-26（Asia/Shanghai）。用户明确要求补上结论与证据对应校验、生成文字中的业务事实一致性检查。

## 实现及边界

support_ai 从当前工作区0.18.0增至0.19.0，版本清单和changelog同步更新。使用既有 `codex/orders-merchant-isolation` 分支；HEAD为 `25a08ee29e23ce1bd479951e5860b44c9dfb2a89`，大量此前未提交变更作为基线保留，没有切换分支、暂存、提交或推送。实现、规格与版本文件相对工作区起始副本的本次增量见 [task.patch](task.patch)，前后指纹及暂存区一致性见 [source-manifest.json](source-manifest.json)。不能用HEAD单独代表此次被测代码。

知识回答和茶类说明均输出独立结论、逐字引文与服务端编号；先进行来源范围、原文子串、隐私、阿拉伯数值及受限业务表述检查，再用配置模型的另一次结构化调用复核每个子结论的支持关系、否定/对象/时间/单位、问题相关性与独立可读性。真实引句不再足以直接放行整段解释。每个给定结论恰好一项判定；缺项、重复或复核故障不会默认通过。

不获支持最多修正一次，修正输入带原候选结论及失败类型；只输出通过的完整要点，来源只对应保留要点。无通过项为明确no_match；技术故障或持续结构错误为error。茶类范围只由通过要点产生，依赖推荐继续受执行器控制，独立任务可以继续。

业务工具文字与已验证知识按完整单元组合，详情由公开DTO固定渲染并保留查询时间，不再使用自由生成的汇总改写业务事实。复核模型可以拒绝整轮，但不能以safe=true改写已验证文字；输出前再次比对完整单元，防止币种替换、库存/状态变化、两款商品互换价格或新增送达承诺。知识路径不允许用文档里的具体商品/订单状态覆盖实时工具事实；一般贸易金额不因包含货币而被一律拒绝。

响应保留原字段并增加grounding：逐步记录通过结论、逐字引文、局部source_id到标题/URL/年份的映射、尝试/拒绝数量与业务单元保护结果。HTTP轮次保存并重放同一核验快照，不重新调用模型；旧历史不补造核验结果。安全拒绝时同步清除新增审计表面中的结论、引用、来源，避免通过grounding字段泄漏被拒内容。

具体实现契约见[回答依据与事实一致性](../../modules/ai-support/grounded-answers.md)。本轮不改变当前CAP阶段、待实施的订单页位置映射或偏好依赖规则，无Migration和新增前端流程。

## 实际验证

解释器为项目 `E:/miniconda/envs/dadashop/python.exe`，Python3.9.25、Django3.2.12。全部Django测试显式使用 `support_ai.test_settings`：default及ai_storage均为隔离SQLite内存库，LocMem缓存；TEMP/TMP为工作区内的专用临时目录。模型使用合成测试替身，没有调用真实模型、业务MySQL、AI PostgreSQL或支付服务。

下表的python代表该项目解释器。实际命令、退出码、环境覆盖和耗时见 [commands.json](commands.json)。

| 命令 | 结果 |
| --- | --- |
| 实施前：`python manage.py test support_ai --settings=support_ai.test_settings --noinput -v 2` | 117项，110通过、6失败、1错误；[原始基线日志](baseline-tests.log)保留原样 |
| `python manage.py check --settings=support_ai.test_settings` | 通过，0个系统问题；[日志](django-check.log) |
| `python manage.py test support_ai.test_grounding support_ai.tests.GraphTests support_ai.test_product_details --settings=support_ai.test_settings --noinput -v 2` | 44项全部通过，其中31项新增定向用例；[日志](focused-tests.log) |
| `python manage.py test support_ai --settings=support_ai.test_settings --noinput -v 2` | 148项，143通过、4失败、1错误；没有新增失败，不能写成整套回归通过；[日志](module-regression.log) |
| `python tools/module_versions.py check` | 通过，16模块、工作区文件均有归属；[日志](module-ownership.log) |
| `git diff --check -- support_ai versions/modules.json versions/changelogs/support_ai.md versions/README.md docs/sdd/modules/ai-support/current-agent.md` | 通过；[日志](diff-check.log)。新增文件另外检查行尾空白和正式文档的本地引用 |

定向用例覆盖：合法原文支持、伪造摘录、外来来源编号、跨茶类借引、真实引句但额外结论无依据、原文否定上下文、无关/依赖前句的结论、新增数字与逗号数列/千分位、复核缺项/重复/超时、一次修正及结构错误、部分要点完整保留、知识冒充实时业务事实、安全拒绝的审计字段清理、无证据不生成、业务价格/币种/库存/状态/承诺篡改、对象价格互换、详情DTO渲染、混合知识订单输出、依赖跳过和独立任务继续，以及HTTP成功保存、幂等重放、无支持no_match和复核故障503不保存成功轮次。

## 既有未通过项

以下5项均在实施前基线出现，保留原断言和失败记录。本轮没有为了全绿放宽业务校验。

| 用例 | 基线及最终现象 |
| --- | --- |
| `GroupedRecommendationTests.test_explicit_subset_and_budget_and_exclusion_are_retained` | 旧断言按12美元直接对比CNY价格，当前转换后多类商品符合；最终仍失败 |
| `MixedTeaIntegrationTests.test_budget_still_applies_to_knowledge_bound_groups` | 旧断言把10美元当10 CNY，只期望绿茶；最终仍失败 |
| `RecommendationIntegrationTests.test_matching_enforces_budget_launch_and_inventory_without_popular_fallback` | 旧断言把50美元当50 CNY，当前更多商品符合；最终仍失败 |
| `SemanticPlanningTests.test_currency_supplement_preserves_budget_category_count_and_evidence` | 旧断言要求source=model，当前规则补充返回rules；最终仍失败 |
| `TaskToolIntegrationTests.test_order_followup_reloads_status_and_keeps_identity_private` | 仍直接读取旧current_order_context中的status，当前上下文契约已改变；基线与最终均KeyError: status |

GraphTests中另有两项基线失败的旧预期要求向模型传旧订单上下文或经过自由汇总；本次因输出约束变化改为检查受控事实原样保留、旧上下文不进入模型，并为知识回答提供实际合成证据。对应测试现已通过。原先“无证据也允许自由回答”的正常回答用例同步改为有证据才回答；不是用假成功掩盖无依据生成。

## 覆盖限制与代价

支持关系复核是同一配置模型的独立调用，合成用例证明校验接线和失败语义，不证明真实模型在开放语义上的准确率。仍可能存在语义误判、知识源错误/过期或受限业务词法规则未覆盖的表达；不能宣称零幻觉、真实世界事实认证或整体grounded效果验收。

正常知识路径增加一次语义复核；触发修正时知识生成/支持复核合计最多4次调用，另有既有安全检查。未执行真实模型耗时、Token或误拒率评测，不能给出线上延迟结论。业务事实保护保证忠实于注册Python工具的文字/DTO，不替代对业务查询、数据质量和计算正确性的验证；价格库存依旧不锁定。

没有运行全项目、浏览器端到端、真实模型/向量检索质量、MySQL/PostgreSQL集成或部署验收。未操作业务数据、Git发布、远端分支或PR。
