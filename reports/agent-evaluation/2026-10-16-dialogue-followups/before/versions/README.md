# Dadashop 当前模块版本

核对日期：2026-10-16（Asia/Shanghai）。机器可读版本以
[modules.json](modules.json) 为准，各模块历史保存在 [changelogs](changelogs/)。
2026-10-15 的核对沿用当时版本号；2026-10-16 先发布智能客服多轮 0.5.0，再升级至有序任务模板 0.6.0，页面脚本为 0.4.1。所有旧版本章节和原有说明均保留。

同日商品模块升级至 0.2.0，增加完整虚拟茶商品及库存批次生成命令。
同日新增 Agent 终端预览，智能客服升级至 0.7.0，知识存储升级至 0.3.1。
随后智能客服升级至 0.8.0，修复分类数量限制，增加六类分组推荐及安全诊断。
智能客服 0.8.1 进一步修复说明与推荐的混合意图漏识别，并绑定介绍范围与商品推荐。

随后智能客服升级至 0.9.0，增加查询翻译、同义扩展、多路召回融合及一次补检；知识存储升级至 0.3.2，支持RAG请求的短Embedding超时。旧版本说明和评测结果继续保留。

## 当前版本清单

| 模块 | 当前版本 | 本次核对状态 | 完整变更记录 |
| --- | --- | --- | --- |
| core · 项目核心 | 0.1.5 | 注册商家助手模块、页面及状态路由 | [core](changelogs/core.md) |
| users · 用户与权限 | 0.1.0 | 保持已有基线 | [users](changelogs/users.md) |
| goods · 商品管理 | 0.4.0 | 六类茶虚拟默认图入库、真实图片优先及统一媒体回退 | [goods](changelogs/goods.md) |
| carts · 购物车 | 0.1.1 | 采购车接入茶类默认图片回退 | [carts](changelogs/carts.md) |
| orders · 订单与报关 | 0.1.1 | 订单／预结算接入统一商品图片选择 | [orders](changelogs/orders.md) |
| pays · 支付 | 0.1.0 | 保持已有基线 | [pays](changelogs/pays.md) |
| news · 内容资讯 | 0.1.0 | 保持已有基线 | [news](changelogs/news.md) |
| inventory · 库存管理 | 0.1.0 | 保持已有基线 | [inventory](changelogs/inventory.md) |
| logistics · 物流 | 0.1.0 | 保持已有基线 | [logistics](changelogs/logistics.md) |
| supplier · 商家与结算 | 0.1.0 | 保持已有基线 | [supplier](changelogs/supplier.md) |
| admin_panel · 平台运营 | 0.3.0 | 补充重排序设置、状态接口和监控统计 | [admin_panel](changelogs/admin_panel.md) |
| support_ai · 智能客服 | 0.9.0 | 查询改写与补检已实测；发现1题重排/选证据退化，尚待修复 | [support_ai](changelogs/support_ai.md) |
| merchant_ai · 商家智能助手 | 0.1.0 | 开放商家入口与模块状态，真实能力暂未接入 | [merchant_ai](changelogs/merchant_ai.md) |
| ai_storage · AI 记忆与知识存储 | 0.3.2 | 本地推理、公开知识查询及请求级Embedding超时 | [ai_storage](changelogs/ai_storage.md) |
| web · 页面与前端资源 | 0.6.0 | 商家智能助手入口、欢迎空态及状态反馈 | [web](changelogs/web.md) |

## 当前代码范围

- 已实现本地 BGE-M3 向量检索、本地 BGE 重排序、证据选择、异常降级及 Agent 监控和运营设置。
- 已有数据库增量迁移包括 `support_ai/0002_agent_observability` 和 `0003_agent_reranking`。
- `support_ai 0.5.0` 增加全分支多轮历史、指代解析和 `0004_conversation_order_context`；行为及限制见 [Agent 多轮对话](../docs/Agent多轮对话.md)。
- `support_ai 0.6.0` 在多轮基础上改用有限意图、固定模板和受控工具执行，加入可复现对照评测；见 [任务模板与评测](../docs/Agent任务模板与对照评测.md)。本次没有新增数据库迁移。
- `support_ai 0.7.0` 新增无需网页的交互式测试入口，独立记录和临时多轮历史；见 [Agent 终端预览](../docs/Agent终端预览.md)。
- `support_ai 0.8.0` 增加按茶类分别推荐、完整任务表达、错误诊断及分组商品追问；见 [Agent 分类推荐](../docs/Agent分类推荐.md)。无新增迁移。
- `support_ai 0.8.1` 修复混合说明与推荐漏识别，按证据验证后的介绍范围查询对应商品，保留完整说明及推荐内容。
- 已实现全站主题统一，对应历史版本 `web 0.3.0`；本次 `web 0.4.0` 在其基础上增加重排序运营界面。
- 已有只读评分诊断工具，复算当前公开知识候选；相关性偏差属于已知问题，不应将服务就绪等同于业务质量验证通过。
- `support_ai 0.9.0` 已接入查询翻译、术语扩展、多路向量召回、RRF融合及一次补检；流程和限制见 [Agent查询改写](../docs/Agent查询改写.md)。随后完成15题双臂真实模型评测：未显示整体收益，发现1题重排/选证据退化；完整问答及口径见 [对照报告](../reports/agent-evaluation/2026-10-16-rag-rewrite/paired-run-1/report.md)。
- 多语言知识版本、按文档语言独立重排序和跨查询分数校准尚未实现，不列为已交付功能。

模块版本、数据库迁移编号和运营设置中的配置修订号含义不同。
运营人员保存配置不会自动产生模块发布版本；本表也不代表创建了新的 Git 发布标签。

## 后续维护

- 现有版本补充说明时，在对应当前版本章节追加条目，保留其原有文字。
- 新功能或修复正式升版时，新建更高版本章节，保留全部旧版本章节。
- 发布版本、路径归属和依赖关系同步维护于 `modules.json`，不要用新内容覆盖旧版本记录。
- 操作流程见 [模块版本管理](../docs/模块版本管理.md)。
