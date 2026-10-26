# tea_saas 现行规格入口

更新：2026-10-23。产品角色为管理员、商家、买家；现有 Django 多 App 与多页面前端继续使用。

本目录区分现行规则、实现观察和历史证据。用户已在审查R01—R11后要求“执行”；本次批准的是规则修订，不代表后端、前端、数据库或部署已经完成调整。

## 阅读顺序与权威

1. [本轮决定和变更清单](rule-review.md)：逐条原规则、新规则、受影响文件、尚待实施事项。
2. [当前状态](product/current-state.md)：源码观察、目标差异和验证／启用边界。
3. [能力清单](catalog.yaml)与[功能映射](product/feature-inventory.yaml)：业务归属；实现模块版本仍以[版本清单](../../versions/modules.json)为准。
4. 对应能力的需求、验收和契约：规则正文的唯一权威。跨域消费者引用规则，不另造订单状态、价格或库存语义。
5. [开放问题](product/open-questions.yaml)、[工作约定](governance/workflow.md)与[下一步](roadmap.md)。

截至本轮静态盘点为8个业务域、28个能力、37项功能、16个实现模块。数量仅为本轮快照；动态清单以YAML为准。

## 主要场景

| 场景 | 现行规格 |
| --- | --- |
| 登录及权限 | [统一登录](modules/identity/unified-login.md)，三类产品角色与内部RBAC权限分别说明 |
| 采购与履约 | [库存预留](modules/trade/stock-reservations.md)、[确认订单](modules/trade/checkout-confirmation.md)、[商家订单](modules/merchant-operations/order-status-filters.md) |
| 基础金额 | [人民币及参考显示](architecture/currency.md)，禁止将外币显示值作为下单价格 |
| 智能客服 | [任务与依赖](modules/ai-support/current-agent.md)、[订单查询](modules/ai-support/capabilities/CAP-AI-003/requirements.md)、[总价推荐](modules/ai-support/total-budget-recommendation.md) |
| 商品与收藏 | [商品详情](modules/catalog-content/product-detail-summary.md)、[商品／商家收藏](modules/catalog-content/capabilities/CAP-CAT-004/requirements.md) |
| 客服历史 | [历史咨询](modules/ai-support/conversation-history.md)，移出列表与数据库删除分开 |
| 人工站内咨询与评价 | [买卖双方咨询](modules/merchant-operations/buyer-merchant-conversations.md)、[购买评价](modules/catalog-content/purchase-reviews.md) |
| 管理与商家能力 | [Agent管理](modules/platform/agent-administration.md)、[平台定位](modules/platform/tea-saas-platform.md)、[商家助手边界](modules/merchant-operations/assistant-entry.md) |

## 历史与实施边界

每项规则只保留一份现行正文。已被完整替换的旧规格直接删除，不建立多版本规格目录。历史evidence仅保留测试、观察和实施证据，不能覆盖现行规则或证明新规则已验收。

本轮不修改运行源码、模块版本、Migration或业务数据。新依赖降级、部分成功、推荐排序、隐藏／取消分离、缺货详情、隐藏恢复及订单序号指代的实现须按对应AC分别验证。纯文档检查不提升验证或部署状态。
