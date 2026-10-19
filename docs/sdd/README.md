# tea_saas SDD 规划入口

2026-10-19运行日志增量：[统一日志与 HTTP 关联](modules/platform/runtime-logging.md)实现安全字段输出、请求编号、耗时、业务错误码与当前 Agent Trace 关联；业务审计、集中检索、自动保留及告警仍为后续范围。

引用定位：`python tools/sdd_refs.py CAP-AI-003`；默认检索当前 SDD 文本，历史证据需加 `--include-evidence`。详见[命令与退出码](../agents/sdd-refs.md)。本地任务、术语和架构决定分别见[任务约定](../agents/issue-tracker.md)、[CONTEXT](../../CONTEXT.md)与[ADR](../adr/README.md)；这些辅助材料不改变本目录的规格权威和能力阶段。

2026-10-19登录视觉更新：[茶文化登录入口](modules/platform/login-visual-identity.md)替换主题图、透明 Logo、三语文案、浏览器标题及图标，支持桌面双栏与移动端短横幅，保持统一登录权限跳转。

2026-10-19工程命名更新：[tea_saas 工程命名](modules/platform/project-identity.md)统一包、文件路径、变量与三语品牌，记录已有资源兼容、历史资料规范化和验证边界；覆盖下文历史名称更新中“工程标识保持兼容”的描述。

2026-10-18本地运行修复：[Redis 认证与采购车配置](modules/platform/redis-runtime.md)，支持环境配置地址和认证，解决已启用 Redis 密码时采购车请求 500；不更改采购车和订单业务规则。

2026-10-18名称与授权更新：当前产品名称统一为“tea_saas”，个人项目源码开放获取、禁止商用，见[平台定位](modules/platform/tea-saas-platform.md)、[非商业使用许可](../../LICENSE)与[本轮验证](evidence/2026-10-18-branding/verification.md)。工程标识和历史证据保持兼容。

2026-10-18订单确认增量：[布局与币种展示](modules/trade/checkout-confirmation.md)，重排地址／商品／摘要，开放三币种参考展示并修复金额长小数，不改变订单结算参数。

2026-10-18交付补充：[跨模块交付验证](evidence/2026-10-18-delivery/verification.md)记录本轮实际检查、版本说明和已知失败；历史SDD静态对账与本轮业务／界面定向验证分开使用，不提升能力阶段。

当前统一入口：[项目聊天更新与 SDD 对账](reconciliation-2026-10-18.md)。已汇总买家／商家 Agent、历史咨询、管理端、前端、身份及 MCP／Skill 的实现和设计边界；当前清单为8域25能力34功能15实现模块，历史对账及测试快照继续按原版本保留。

2026-10-18 工具增量：[MCP 与 Skill 接入](../MCP与Skill接入.md)提供本地只读商品详情和仓库交付 Skill；[商品搜索 MCP 详细设计](modules/ai-support/search-products-design.md)为后续草案，不改变其他切片评审状态。

2026-10-18商家修复：[商家商品预览与标签页身份隔离](modules/catalog-content/merchant-preview.md)，查看留在商家工作台，身份不从共享存储跨标签页回填。

2026-10-18增量：[统一登录与平台权限隔离](modules/identity/unified-login.md) 已按用户请求实施。当前规则及验证见增量文档；以下历史基线和证据不覆盖本次改动，不代表本次已发布。

规划日期：2026-10-16（Asia/Shanghai）。SDD 指 Specification-Driven Development（规格驱动开发）。

本目录保存**存量项目渐进式 SDD 规划与能力规格材料**。2026-10-16 已由 dengbofu 确认首个 AI 查询切片的核心业务选项，阶段为 `SPEC_REVIEW`，完整条款尚在评审。同日按用户明确请求新增并实施收藏与足迹 `CAP-CAT-004`，阶段为 `IMPLEMENTING`，附定向测试及本地迁移证据，待人工审阅；没有登记生产发布批准。

收藏与足迹及本次聊天对账后，当前目录登记25个能力、34项功能。早期24／28及25／29分别属于历史快照，不代表当前完整清单。

## 从这里阅读

2026-10-18平台定位：[tea_saas](modules/platform/tea-saas-platform.md)，统一三语名称与产品范围，经营看板回归销售与订单履约指标。

2026-10-18客服增量：[历史咨询入口与切换续聊](modules/ai-support/conversation-history.md)，提供本人会话列表、记录分页、草稿及历史提示，继续沿用模型上下文预算。

2026-10-18分类预览：[首页茶类分类预览](modules/catalog-content/catalog-preview.md)，替换四个采购场景按钮和静态茶类，按数据库实际分类筛选。

2026-10-18卡片增量：[买家商品卡片操作分层](modules/catalog-content/card-interactions.md)，固定主／次操作区域并移除遮挡层，见[验证记录](evidence/2026-10-18-card-actions/verification.md)。

| 文件 | 用途 |
| --- | --- |
| [当前项目聊天对账](reconciliation-2026-10-18.md) | 各聊天增量、当前实施状态、证据范围和剩余差异 |
| [当前买家 Agent](modules/ai-support/current-agent.md) | 六类任务、推荐／知识／订单／偏好／历史与工具边界 |
| [商家助手入口](modules/merchant-operations/assistant-entry.md) | 已实现入口与未实现经营能力 |
| [Agent 运营管理](modules/platform/agent-administration.md) | 权限、配置、知识库占位与开关交互 |
| [页面补充交互](modules/platform/interface-increments.md) | 跨商品、采购、经营及管理端的界面变化 |
| [茶类虚拟默认图片](modules/catalog-content/image-fallback.md) | 数据库六类茶图入库、真实图片优先、导入迁移与验证 |
| [CAP-CAT-004 收藏与足迹](modules/catalog-content/capabilities/CAP-CAT-004/requirements.md) | 本次规则、范围、接口、验收及迁移 |
| [收藏与足迹验证](evidence/2026-10-16-buyer-activity/verification.md) | 定向验证、浏览器检查和本地迁移结果 |
| [roadmap.md](roadmap.md) | 推进顺序、交付物、完成条件和下一步 |
| [reconciliation.md](reconciliation.md) | 2026-10-16历史对账与原验证范围；当前增量见新对账 |
| [catalog.yaml](catalog.yaml) | 8 个建议业务模块、25 个候选／活动能力及 15 个版本模块的归属 |
| [product/current-state.md](product/current-state.md) | 已观察事实、推断、差异与风险 |
| [product/source-manifest.yaml](product/source-manifest.yaml) | 参考项目与本项目的材料来源、核查边界 |
| [product/feature-inventory.yaml](product/feature-inventory.yaml) | 功能、页面、API、代码到唯一主能力的初步映射 |
| [product/open-questions.yaml](product/open-questions.yaml) | 未决业务问题、影响范围和阶段阻塞 |
| [architecture/context.md](architecture/context.md) | 当前系统、数据所有权和跨模块依赖 |
| [governance/workflow.md](governance/workflow.md) | 能力生命周期、变更分流、文档与证据要求 |
| [CAP-AI-003 需求草案](modules/ai-support/capabilities/CAP-AI-003/requirements.md) | 建议试点：买家通过 AI 客服查询本人订单 |
| [CAP-AI-003 验收草案](modules/ai-support/capabilities/CAP-AI-003/acceptance.yaml) | 可评审的 Given／When／Then 场景 |
| [CAP-AI-003 评审包](modules/ai-support/capabilities/CAP-AI-003/review.md) | 已确认决策、逐 AC 覆盖、实现差异及发现证据 |
| [CAP-AI-003 技术设计](modules/ai-support/capabilities/CAP-AI-003/design.md) | 执行顺序、只读边界、会话事务及兼容／回滚 |
| [CAP-AI-003 接口契约](modules/ai-support/capabilities/CAP-AI-003/api-contract.yaml) | OpenAPI目标草案、字段、错误码和幂等语义 |
| [CAP-AI-003 当前接口观察](modules/ai-support/capabilities/CAP-AI-003/api-observed.yaml) | 当前错误形态／200行为；与目标契约分开，防止误读为已实现 |
| [CAP-AI-003 脱敏方案](modules/ai-support/capabilities/CAP-AI-003/redaction.md) | 引用识别／替换、模型DTO、完整响应与历史边界 |
| [CAP-AI-003 页面状态](modules/ai-support/capabilities/CAP-AI-003/screen-spec.md) | 16种状态、404区分、恢复、重试和历史提示 |

## 采用方式

先把现有功能及其代码证据放进清单，再选定一条可验收的业务切片，逐步补需求、权限、状态、接口和测试。存量代码是待核实的实现资产；存在源码、演示页面或历史测试报告，均不自动等于规格已确认或已发布。

`CAP-AI-003` 已由 `DISCOVERY` 进入 `SPEC_REVIEW`；其余 23 项只登记为 `candidate`。全部模块为 `REGISTERED`，表示建议边界已登记，不宣称全量映射完成。功能清单是按主要业务入口采样的初步盘点，尚未逐端逐操作穷尽。

参考 store-ai-tp 的：模块／能力分离、候选／活动分离、跨端共同规格、阶段准入、未知事项管理、规格与证据分离。针对 tea_saas 简化为：

- 将候选能力集中放在 `catalog.yaml`，只为当前试点创建活动能力目录。模块增长后再拆 `overview.md`、`capability-map.yaml` 等文件，并一次性迁移权威入口。
- 用已有页面／API 盘点承接入口，暂不为每个菜单生成六件套。
- 保持现有 Django App、API 路径和模块版本管理；SDD 业务域是规则归属，不是本轮代码重组方案。
- 不继承来源项目的学习业务、Java／Vue 架构、人员、分支制度、已批准阶段或工具命令。

## 当前状态与边界

| 维度 | 本轮状态 |
| --- | --- |
| 规划和初步映射 | 已编写，可评审 |
| 首个切片业务负责人 | dengbofu；技术评审人待指定 |
| 首个切片 | `SPEC_REVIEW`，规格 `0.2.0` |
| 设计材料 | `0.1.0`草案已补齐，未实施或通过技术／体验评审 |
| 其他能力 | `candidate`，不构成首期交付承诺 |
| 自动阶段检查器 | 未接入；阶段条件目前人工核对 |
| 本次全SDD对账 | 全部24能力已按源码核对；补齐4项现有功能，清单共28项，尚非逐操作全量验收 |
| 本次隔离回归 | 101项中98通过、3项需真实PostgreSQL而跳过；运行期间源码哈希稳定，外部网络尝试0 |
| 本次对账探针 | 5项观察；订单404/英文编号脱敏/旧历史投影仍有差异，当前没有目标error_code |
| 历史发现证据 | 原61/64、64/64和8项探针分别保留，不与本次结果混算或改写 |
| 目标环境／真实模型／浏览器验收 | 未执行 |
| 部署、发布 | 本轮未执行 |

本目录中的 YAML 是 tea_saas 的规划数据，不宣称兼容 store-ai-tp 检查器。后续若引入检查器，再明确本项目 schema、固定权威路径、路径边界和测试；不能复制一个 profile 文件后声称门禁已生效。

## 下一次工作入口

先阅读 [当前评审包](modules/ai-support/capabilities/CAP-AI-003/review.md)，评审完整 REQ/RULE/AC、已补齐的接口／脱敏方案与页面状态。发现阶段的 `Q-001／002／003／012` 已按本切片范围解决；后续 `BUILD_READY` 仍需解决 `Q-011`（技术评审及目标环境）和 `Q-013`（持久化访问／保留／删除）。达到 `BUILD_READY` 后再按实施授权修复差异。

现有系统可继续按已授权范围维护。无规格变化的修复采用聚焦检查；遇到尚未确定的业务规则，先登记差异，不把现有实现直接追认为正确业务规则。
