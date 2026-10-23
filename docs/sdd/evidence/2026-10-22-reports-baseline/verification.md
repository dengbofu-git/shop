# reports 当前工作区基线及接口关联核验

日期：2026-10-22（Asia/Shanghai）。用户要求：以当前最新工作区作为基线，重新测试、记录，并核对 reports 相关部分与其他接口的实际关联。

## 基线与范围

HEAD 为 `25a08ee29e23ce1bd479951e5860b44c9dfb2a89`，分支 `codex/orders-merchant-isolation`。本机存在大量已有未提交改动及其他 worktree，本批直接核验当前工作区，不能用 HEAD 单独复现，也不声称它等于远端最新 main 或发布版本。开始时登记版本为 support_ai 0.15.0、goods 0.6.1、core 0.7.0、web 0.29.4。

开始时对仓库 1240 个路径记录字节 SHA256、大小或已有缺失状态，并记录模块版本、Git 状态及暂存区差异指纹，见 [baseline.json](../../../../reports/agent-evaluation/2026-10-22-reports-baseline/baseline.json)。结束比对见 [workspace-integrity.json](../../../../reports/agent-evaluation/2026-10-22-reports-baseline/workspace-integrity.json)。既有未提交实现作为被测对象，不混入本批修改。

收尾检测到 9 个范围外路径在核验期间发生变化：站内咨询 CSS/JS、买家与商家消息页、共用 engagement_assets、对应 SDD 以及版本说明/清单/changelog；web 增至 0.29.5。本批没有写入这些路径，保持其现场，并记录前后指纹。support_ai、goods、客服页面/脚本等本次关联源码及原始 reports 载荷均未变化，暂存区与 HEAD 未变化。针对共用页面资产变化，最后另跑 BuyerShellTests 3 项通过；不据此声称整仓所有文件保持基线一致。

使用 `<PYTHON_ENV>/python.exe`（Python 3.9.25 / Django 3.2.12）。数据库配置明确指定 `support_ai.test_settings`，default 与 ai_storage 均为隔离 SQLite 内存库，缓存为 LocMem；图片注册只写测试库并只读现有 media 文件。合成探针禁止 socket 连接，模型路径使用测试替身或固定问候回复。业务 MySQL、AI PostgreSQL、真实用户历史及真实模型质量不在本批动态验证范围。

## 实际关联

| 入口 | 当前数据流 | 与 reports 的关系 | 本轮结果 |
| --- | --- | --- | --- |
| `manage.py agent_preview` | Command → PreviewSession → fixed_result 或 build_graph → 内存轮次 + 脱敏 JSONL | 默认自动创建 `reports/agent-preview/`，可用 `--log-dir` 改目录 | 合成问候经真实 CLI 生成新日志；默认目录创建、嵌套文本脱敏及不写客户会话通过 |
| `POST /v1/support/chat/` | views.chat → fixed_result / 同一 Agent 图和商品工具 → context.commit_turn → SupportConversation / SupportTurn | 没有自动进入 preview 日志目录；网页客服记录以数据库为准 | 已认证问候、同 request_id 成功重放不重复写入、商品推荐共用工具通过 |
| `GET /v1/support/conversations/` 与 UUID 详情 | conversation_list / conversation_detail → 本人会话数据库 | 不读取 reports 里的旧 JSONL | 列表、详情均 200；其他用户读取详情 404 |
| `GET/PUT/DELETE /v1/support/preferences/` | views.preferences → ai_storage.BuyerMemory | 不把 reports 日志当偏好来源 | 合成买家三种操作均 200；匿名 chat 401 |
| `client/static/js/buyer-support.js` | `/v1/support/` 下的 chat、preferences、conversations；商品卡片图片请求 SKU image 接口 | 页面没有报告目录浏览或导入功能 | 前端调用字符串与 9 条 URL 的 Django resolver 绑定检查通过；未做浏览器交互验收 |
| `register_tea_images --manifest ...` | reports 中的 plan.json → 图片文件/哈希校验 → Catalog.fallback_image | reports 是一次登记的输入清单；不是每次请求图片的读取源 | 当前清单 6 个文件哈希吻合；预览零更新、apply 两次幂等、6 类图片实际接口返回及哈希吻合 |
| 图片、商品列表、详情、购物车与订单 DTO | 数据库中的图片路径 → goods.images → media 文件 | 已登记后靠数据库路径和 media 提供图片，不靠反复读取 reports 清单 | goods.test_images 的 8 项全部通过，覆盖上传覆盖、删除回退、分类隔离、列表/详情/采购车及订单 DTO；完整订单业务链未测 |
| `seed_virtual_tea_products` | 显式数据库身份检查 → 商品/库存创建，同时写 before/plan/fixture/integrity/manifest 等批次文件 | reports/virtual-products 是造数记录与快照输出；运行时商品来自数据库 | 合成计划 100 项；SQLite 拒绝写入；两个数据库身份不匹配检查通过。未实际执行 MySQL 造数，不能声称当前整批写入成功 |
| `evaluation/compare.py` 与 `report.py` | 读取 archive 内冻结输入/旧源码/旧输出；前者进行模型对照，后者汇总 | 确实依赖历史 reports 输入，不是网站 HTTP 接口 | 归档及默认输入存在；report 在临时副本中成功生成 summary 与 Markdown；没有重跑真实模型对照 |
| 旧 grouped replay / 15 题 reporter | 历史事件回放或历史输出排版 | 部分路径和结论仍固化在 10 月 16 日 | 存在下列已复现问题，不能直接当当前基线工具 |

监控与 reports 预览日志也不同：`support_ai/telemetry.py` 使用 AgentSpan 等数据库记录，现有运营权限、配置、监控回归随 support_ai 测试执行。固定问候不需要生成 AgentSpan。此次没有把 JSONL 文本日志当成 HTTP 监控记录。

## 执行结果

命令、退出码和环境详见 [checks.json](../../../../reports/agent-evaluation/2026-10-22-reports-baseline/checks.json)，可审阅的实际临时探针源码见 [procedures.md](../../../../reports/agent-evaluation/2026-10-22-reports-baseline/procedures.md)。下表中的 `python` 代表上述项目 Conda 解释器。

| 实际命令 | 结果 |
| --- | --- |
| `python manage.py check --settings=support_ai.test_settings` | 通过，0 个系统问题 |
| `python manage.py test support_ai goods.test_images goods.test_seed_identity --settings=support_ai.test_settings --noinput -v 2` | 首次有临时目录权限错误；使用工作区内 TEMP/TMP 后 127 项中 123 通过、4 失败，0 error；没有删除或掩盖首轮日志 |
| `python client/tests/repository-cleanup-contract.py RepositoryCleanupTests.test_historical_git_content_is_identical_and_complete RepositoryCleanupTests.test_current_comparison_defaults_have_their_historical_inputs -v` | 2 项通过：205 份归档内容与清单一致，评测默认输入可找到 |
| `python .scratch/reports-baseline-20261022/probe_reports.py` | 9 项通过，包括正常功能和已知缺陷复现；通过缺陷复现断言不等于工具健康 |
| `python .scratch/reports-baseline-20261022/probe_current_contract.py` | 4 项当前契约检查通过，解释既有 4 项旧断言为何失效；原测试文件和失败日志均保留 |
| `python manage.py test support_ai.tests.BuyerShellTests --settings=support_ai.test_settings --noinput -v 2` | 检测到范围外页面资产变化后复测，3 项通过，覆盖买家页面共用导航、客服页面控制及未登录拒绝 |
| `python tools/module_versions.py check` | 通过，16 模块，工作区文件均有归属 |
| `git diff --check -- reports/README.md reports/agent-evaluation/README.md` | 通过；另核对本批索引和报告中的本地链接均存在 |

首轮运行额外设置了 `SUPPORT_RAG_QUERY_ENABLED=false` 并使用沙箱默认临时目录，故不作为最终运行环境；复测取消这个业务开关覆盖，采用现有测试设置及工作区可写临时目录。8 项图片用例首次在准备/清理目录时共报 16 个 error，复测后全部通过，属于执行环境问题。

## 当前发现

### RPT-001：分组回放脚本仍指向归档前路径

`support_ai/evaluation/replay_grouped_preview.py` 固定读取：

```text
reports/agent-evaluation/2026-10-16-grouping/before/20261016-114613-cf6a9b60bb8047dead1a4663ec911451.jsonl
```

该文件实际已在 `reports/archive/2026-10-16/agent-evaluation/2026-10-16-grouping/before/`。本次调用 main，在模型执行前复现 FileNotFoundError。指定新的 `--output` 也不能改变固定的输入路径。建议后续显式提供历史输入参数，并为每次新运行选择独立输出目录；当前没有修复或删除归档。

### RPT-002：15 题报告器固化历史人工判断与版本

`support_ai/evaluation/report_scenario_suite.py` 的 REVIEWS 保存固定的逐题人工结论，Markdown 还写死 support_ai 0.8.1、2026-10-16、旧模型及多项旧汇总数字。为了验证是否能复用于当前批次，本次在临时目录构造 15 条自动检查全部为 true、零模型调用的合成结果，报告器仍输出 6 个“失败”和旧版说明。

这说明它能排版当次历史记录，但不能自动评审新结果。合成输出只在临时目录存在并随测试清理，正式证据仅保存输入说明和复现观察，避免把合成报告当成真实模型成绩。后续需让人工复核随每次 run 保存、版本/日期/自动统计取本轮 manifest，或将此脚本明确限制为历史报告重建。

`evaluation/report.py` 同样面向 0.5.0/0.6.0 的固定历史对照，虽然能生成文件，也不应直接复用为 0.15.0 的通用报告器。当前 baseline 记录为独立批次，没有覆盖这些旧结果。

### RPT-003：预览返回版本无法标识当前模块

当前 `support_ai/preview.py` 的 PREVIEW_RUNTIME_VERSION 为 0.10.0，`status()` 将它返回为 agent_version；`versions/modules.json` 中 support_ai 为 0.15.0。探针确认日志也记录 0.10.0。即使它原本用于表示预览协议，也不能用此字段证明实际 Agent 模块版本。本批使用模块清单和源码指纹标识基线。建议后续区分 preview 协议版本与实际模块版本。

### RPT-004：4 个既有回归断言未跟随当前金额与规则解析契约

依据为 [当前金额规格](../../architecture/currency.md) 与 [ADR-0003](../../../adr/0003-cny-base-currency.md)，不是凭测试失败修改业务预期。复测仍保留以下 4 个失败；新增合成检查仅核验当前行为，没有修改原用例或业务实现。

| 原失败用例 | 旧断言 | 当前契约与本轮观察 |
| --- | --- | --- |
| `GroupedRecommendationTests.test_explicit_subset_and_budget_and_exclusion_are_retained` | 12 美元直接以商品 price ≤ 12 筛选，只返回绿茶、白茶 | 基础价 CNY，12 USD 换算上限 85.71 CNY；返回绿茶、白茶、乌龙茶、黄茶、黑茶，红茶仍被排除，价格均在上限内 |
| `MixedTeaIntegrationTests.test_budget_still_applies_to_knowledge_bound_groups` | 10 美元只返回绿茶 | 换算上限 71.42 CNY，绿茶与红茶均符合；原条件仍保留 10.00 USD，不把用户输入改写为人民币 |
| `RecommendationIntegrationTests.test_matching_enforces_budget_launch_and_inventory_without_popular_fallback` | 50 美元只允许 price 40，不允许 price 100 | 50 USD 上限 357.14 CNY，40 与 100 CNY 均可售；50 CNY 则只返回 40 CNY；10 CNY 无匹配；下架、零库存和完全预留商品继续被排除 |
| `SemanticPlanningTests.test_currency_supplement_preserves_budget_category_count_and_evidence` | 补充“美元”必须调用模型，source=model | 当前确定性规则补充币种，source=rules、模型调用 0；仍保留绿茶、单价上限 50 USD、两款数量及已完成状态 |

这些结果支持“旧测试口径需要更新”的判断，但不能把整套相关回归写成已通过；当前原回归仍有 4 项红灯。

## 交付与限制

本批产出为测试记录、合成 CLI 日志和 reports 索引文档增量，没有修改业务实现、旧评测载荷或已有测试断言。纯证据/说明增量不升实现模块版本。

未执行真实模型/重排序/向量库质量评测、MySQL 造数或迁移、真实订单/支付流程、浏览器端到端验收、远端同步、Git 提交、推送、PR 或部署。动态检查使用 Django test client 与测试模型替身；代码关联和文件存在不能当作整站业务验收。

本轮已证明 reports 部分内容确有工具用途，同时确认了历史工具关联未完整更新。不能据此直接将整个 reports 删除；清理历史材料前，应先处理仍引用它们的工具与文档，并保留需要复核的历史证据。

2026-10-23交付整理：公开副本仅将本机绝对路径规范化为 `<WORKSPACE>`／`<PYTHON_ENV>`，未改变命令参数、时间、失败结果及测试结论；原始字节和SHA256保存在本地交付备份。此历史结果不作为本轮通过证据。
