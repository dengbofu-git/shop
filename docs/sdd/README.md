# Dadashop SDD 规划入口

规划日期：2026-10-16（Asia/Shanghai）。SDD 指 Specification-Driven Development（规格驱动开发）。

本目录保存**存量项目渐进式 SDD 规划与能力规格材料**。2026-10-16 已由 dengbofu 确认首个 AI 查询切片的核心业务选项，阶段为 `SPEC_REVIEW`，完整条款尚在评审。同日按用户明确请求新增并实施收藏与足迹 `CAP-CAT-004`，阶段为 `IMPLEMENTING`，附定向测试及本地迁移证据，待人工审阅；没有登记生产发布批准。

收藏与足迹增量使当前目录共登记25个能力、29项功能。下列对账文件中24／28的数量仅指较早基线，原证据不覆盖新增实现。

## 从这里阅读

| 文件 | 用途 |
| --- | --- |
| [茶类虚拟默认图片](modules/catalog-content/image-fallback.md) | 数据库六类茶图入库、真实图片优先、导入迁移与验证 |
| [CAP-CAT-004 收藏与足迹](modules/catalog-content/capabilities/CAP-CAT-004/requirements.md) | 本次规则、范围、接口、验收及迁移 |
| [收藏与足迹验证](evidence/2026-10-16-buyer-activity/verification.md) | 定向验证、浏览器检查和本地迁移结果 |
| [roadmap.md](roadmap.md) | 推进顺序、交付物、完成条件和下一步 |
| [reconciliation.md](reconciliation.md) | 全部24能力与当前源码的对账、28项功能、已知差异及本次验证 |
| [catalog.yaml](catalog.yaml) | 9 个建议业务模块、24 个候选／活动能力及 14 个版本模块的归属 |
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

参考 store-ai-tp 的：模块／能力分离、候选／活动分离、跨端共同规格、阶段准入、未知事项管理、规格与证据分离。针对 dadashop 简化为：

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

本目录中的 YAML 是 dadashop 的规划数据，不宣称兼容 store-ai-tp 检查器。后续若引入检查器，再明确本项目 schema、固定权威路径、路径边界和测试；不能复制一个 profile 文件后声称门禁已生效。

## 下一次工作入口

先阅读 [当前评审包](modules/ai-support/capabilities/CAP-AI-003/review.md)，评审完整 REQ/RULE/AC、已补齐的接口／脱敏方案与页面状态。发现阶段的 `Q-001／002／003／012` 已按本切片范围解决；后续 `BUILD_READY` 仍需解决 `Q-011`（技术评审及目标环境）和 `Q-013`（持久化访问／保留／删除）。达到 `BUILD_READY` 后再按实施授权修复差异。

现有系统可继续按已授权范围维护。无规格变化的修复采用聚焦检查；遇到尚未确定的业务规则，先登记差异，不把现有实现直接追认为正确业务规则。
