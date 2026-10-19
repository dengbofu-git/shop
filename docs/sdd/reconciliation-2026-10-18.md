# tea_saas 项目聊天更新与 SDD 对账

对账日期：2026-10-18（Asia/Shanghai）。范围为当前 tea_saas 项目已识别聊天中的功能增量、当前工作区源码和已有证据，包括买家 Agent、商家助手、管理端、前端、身份权限与 MCP／Skill。本文接续 [2026-10-16 基线](reconciliation.md)，旧测试和批准记录保留原时间与版本，不作为本次重新通过的结论。

当前登记为 8 个业务域、25 个能力、34 项功能和 15 个实现版本模块。新增商家助手能力 CAP-MER-004，映射 merchant_ai 实现模块；新增历史咨询、推荐理由、商家助手入口、MCP 详情、开发交付 Skill 和平台交易总览六项功能。业务域仍是规则归属，实现版本仍以 `versions/modules.json` 为准。

## 聊天更新到规格的对应

聊天标题按应用中的原名列出。聊天结果是变更线索，当前源码决定实施现状；只有关联文件中保存的证据能支持相应版本的验证结论。

| 聊天 | 涉及更新 | SDD 归属和处理 | 当前边界 |
| --- | --- | --- | --- |
| 前端 | 卡片主次操作、禁用溯源、去掉 GI、商品名与规格分离、首页／采购页每页10件、全部分类、收藏空态、采购车币种、详情排版、平台改名 | CAP-CAT-001／004、CAP-TRD-001、CAP-PLAT-002；关联卡片、分类预览、页面补充与 SaaS 定位规格 | USD／AED／SAR 是展示参考换算；GI 删除不能解释成真实认证审核；库存口径未统一 |
| 功能补全 | 统一登录和权限分流、平台账号 API 隔离、商家商品只读预览、标签页身份隔离 | CAP-IAM-001／003、CAP-CAT-002、CAP-PLAT-001／002；复用统一登录及商家预览规格 | 不将局部鉴权修复扩大为全站对象权限已解决 |
| 管理员端 | 交易总览、三导航统一外壳、平台／商家销售口径、知识库提交占位、四个开关仅点框切换 | CAP-PLAT-001／002、CAP-MER-002、CAP-AI-004；复用总览和销售对账，补 Agent 管理规格 | 平台流水不是支付账本；上传按钮禁用，无实际上传／入库 API |
| rag | RAG 改写、多查询、一次补检、推荐主题继承与理由解释、真实评测、Enter发送、历史咨询与分页续聊 | CAP-AI-001／002／003／004、CAP-KNOW-001／002；补当前 Agent 能力说明、历史接口观察、测试缺口 | 运行状态与模型质量分开；历史入口不扩大模型上下文，不修复列表指代和任务拆分缺陷 |
| agent设计 | 长期偏好、受控工具、会话和推荐设计 | CAP-AI-001、CAP-KNOW-001；关联当前能力与源码 | 偏好由本人显式维护；收藏／足迹和助手文字不自动保存为偏好 |
| agent设计说明 | 商家入口 v0.1；TXT／PDF／Excel 导入、文案／图片／视频等后续方案 | 新增 CAP-MER-004；区分已实现入口与未实现经营能力 | 无聊天、上传、生成、入库接口；不将讨论中的方案变成已授权业务规则 |
| agent-商家 | 点击助手404，本地服务重载后恢复 | CAP-MER-004；记录路由和运行重载边界 | 这是历史本地预览排障，不代表当前端口或服务仍在运行 |
| 针对当前的tea_saas项目，分析是否可以在MCP和Skill方面进行深化设计？ | tea-saas-change-delivery、get_product_details 实现及 search_products 设计 | CAP-PLAT-003、CAP-AI-001；登记 Skill／MCP 当前事实，保留搜索草案 | 本地 stdio、独立 Python 环境；未改用户级配置，无远程认证；搜索未实现 |
| git | Git 规范、hook、版本、提交／PR 历史 | CAP-PLAT-003；引用现有事实源，不把历史交付授权转移到本次 | 不联网刷新 PR 状态，不声称远端保护已启用；本次不提交／推送 |
| 参考E:\实习\store-ai-tp，对tea_saas项目进行sdd规划 | 初始业务域、目标接口、脱敏和页面状态、旧对账 | 保留历史基线，当前入口转到本次增量 | CAP-AI-003 仍 SPEC_REVIEW；未补写技术评审人或批准 |

“并发说明”“概念说明”等聊天主要解释其他项目或通用概念，没有据此将 Store 的 GENERAL／ABSTAIN、Java 接口、组织或治理规则导入 tea_saas。“为什么codex总是闪退”属于工具排障，不产生站内业务能力。

## 当前 Agent 能力

买家六类有限意图及其编排、推荐、知识检索、订单读取、偏好、会话历史、终端预览和观测见 [当前 Agent 规格](modules/ai-support/current-agent.md)。商家独立入口见 [商家助手入口](modules/merchant-operations/assistant-entry.md)；管理端配置、知识库占位及开关交互见 [Agent 运营管理](modules/platform/agent-administration.md)。

CAP-AI-003 的旧历史观察已经过期：当前新增本人咨询列表和 sequence 分页，历史 GET 会递归处理字符串脱敏；成功请求 replay 仍直接使用保存响应，未获得同等读取投影。仅历史接口新增 is_active 检查，chat／preferences 的共享 _buyer 未同步增加，不能声称全部客服接口已拒绝停用账号。目标订单404、有限错误码、临时 ctx 引用和英文编号完整脱敏仍有差异。

## 已有关联验证

| 增量 | 已有材料 | 使用限制 |
| --- | --- | --- |
| 统一登录与卡片／预览 | evidence/2026-10-18-unified-login、card-actions、catalog-preview、catalog-pagination、merchant-preview | 按各文件的版本、合成数据和浏览器范围使用，不合并成全站验收 |
| 平台总览和销售口径 | modules/platform/trading-overview.md、sales-reconciliation.md、evidence/2026-10-18-platform-overview | 金额是当次只读快照；统计不是支付／退款账本 |
| SaaS 定位调整 | evidence/2026-10-18-tea-saas/verification.md | 不表示租户、订阅计费或真实资金服务已实现 |
| MCP／公开详情／Skill | evidence/2026-10-18-mcp-skill/verification.md | 对应22项 Django 和9项 MCP定向验证；相邻回归有2项原实现也可复现的失败 |
| 历史咨询和 Enter | modules/ai-support/conversation-history.md、CAP-AI-003/screen-spec.md | 原增量只有静态／配置检查；尚无完整分页、身份切换及浏览器交互自动化证据 |
| RAG／多轮质量 | reports/archive/2026-10-16/agent-evaluation/2026-10-16-rag-rewrite/paired-run-1、2026-10-16-dialogue-followups/live-run-1 | 0.9.0和0.10.0限定样本；不能当作当前0.11.1效果复测 |

## 保留的问题和后续验收

- RAG 对照未显示整体收益，重排与同来源片段限额仍可能丢失关键证据；服务 ready 只表示可用，不表示回答质量达标。
- 推荐连续序号追问可能丢失原列表，范围／预算补充和分组理由可能重复拆任务。详情读取共享服务不自动修复这些问题。
- 历史列表和详情需补跨账号、游标、停用账号、分页边界、恢复失败和并发切换测试；默认6轮兼容不等于展示永远只有6轮。
- 订单404、完整脱敏、重放投影、模型临时引用和全部页面状态继续按 CAP-AI-003 评审，不将部分增量提升为整个切片已验收。
- 对象级权限、可信支付、库存权威量、跨商家履约、真实经营指标及数据保留策略继续留在开放问题中。
- 商家批量导入、生成图片／视频、经营工具与 MCP 商品搜索仍为后续设计；知识库上传仍为禁用占位。

本次只更新 SDD。静态一致性结果和源码指纹见 [本次记录](evidence/2026-10-18-project-chat-sdd/verification.md)；未运行模型回放、业务库迁移、全站测试、部署或发布。
