# tea_saas 现行规格入口

更新：2026-10-30。产品角色为管理员、商家、买家；现有 Django 多 App 与多页面前端继续使用。

本目录区分现行规则、实现观察和历史证据。2026-10-23用户在审查R01—R11后要求“执行”，该记录确认业务规则修订；后续实现、验证及启用分别按对应快照说明，本次提纯不新增业务批准。

## 阅读顺序与权威

1. [当前状态](product/current-state.md)与[SDD 提纯审查](product/sdd-purification-review.md)：先确认本项目场景、当前源码、来源噪音及待讨论分支。
2. [既有决定和变更清单](rule-review.md)：R01—R11 的确认范围；原日期实施说明不替代当前状态。
3. [能力清单](catalog.yaml)与[功能映射](product/feature-inventory.yaml)：业务归属；实现模块版本仍以[版本清单](../../versions/modules.json)为准。
4. 对应能力的需求、验收和契约：规则正文的唯一权威。跨域消费者引用规则，不另造订单状态、价格或库存语义。
5. [开放问题](product/open-questions.yaml)、[工作约定](governance/workflow.md)与[下一步](roadmap.md)。

工程交付与本地收尾设计见[本地收尾](governance/local-delivery-closeout.md)：分别记录远端合入、原工作区核销和临时资源回收；现有 tools/local_closeout.py 提供 audit／plan／apply 与受审阅的逐资源回收，全自动发现并删除工作区仍未开放，不改变根协作规则的授权边界。

2026-10-28用户确认[模型 Agent 数据访问统一经 MCP](architecture/agent-data-access.md)并要求“运行”。应用入口已完成源码迁移及隔离验证，见[运行设计](modules/ai-support/mcp-runtime.md)；[全项目改造清单](modules/ai-support/mcp-migration.md)保留实施前差异和顺序。业务启用、真实模型质量和发布未据此完成。

截至2026-10-30静态盘点为8个业务域、27个能力、36项功能、15个实现模块。数量仅为本轮快照；动态清单以YAML为准。来源项目阶段、原型审批链和模板套数不作为本项目开发要求。

## 主要场景

| 场景 | 现行规格 |
| --- | --- |
| 登录及权限 | [统一登录](modules/identity/unified-login.md)，三类产品角色与内部RBAC权限分别说明 |
| 采购与履约 | [库存预留](modules/trade/stock-reservations.md)、[确认订单](modules/trade/checkout-confirmation.md)、[商家订单](modules/merchant-operations/order-status-filters.md) |
| 基础金额 | [人民币及参考显示](architecture/currency.md)，禁止将外币显示值作为下单价格 |
| 智能客服 | [任务与依赖](modules/ai-support/current-agent.md)、[订单查询](modules/ai-support/capabilities/CAP-AI-003/requirements.md)、[总价推荐](modules/ai-support/total-budget-recommendation.md) |
| Agent 数据入口 | [统一 MCP 规范](architecture/agent-data-access.md)、[迁移清单](modules/ai-support/mcp-migration.md)，后端领域服务保留数据库职责 |
| 商品与收藏 | [商品详情](modules/catalog-content/product-detail-summary.md)、[商品／商家收藏](modules/catalog-content/capabilities/CAP-CAT-004/requirements.md) |
| 客服历史 | [历史咨询](modules/ai-support/conversation-history.md)，移出列表与数据库删除分开 |
| 人工站内咨询与评价 | [买卖双方咨询](modules/merchant-operations/buyer-merchant-conversations.md)、[购买评价](modules/catalog-content/purchase-reviews.md) |
| 管理与商家能力 | [Agent管理](modules/platform/agent-administration.md)、[平台定位](modules/platform/tea-saas-platform.md) |

## 历史与实施边界

每项规则只保留一份现行正文。已被完整替换的旧规格直接删除，不建立多版本规格目录。历史evidence仅保留测试、观察和实施证据，不能覆盖现行规则或证明新规则已验收。

本次提纯仅修改文档，不修改运行源码、模块版本、Migration或业务数据。依赖隔离、部分成功、CP-SAT、取消／隐藏分离已有不同范围实现；缺货详情、隐藏恢复及订单序号映射等剩余差异见当前状态。所有规则仍须按对应AC分别验证，纯文档检查不提升验证或部署状态。
