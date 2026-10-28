# tea_saas当前模块版本清单

2026-10-21历史评价启用：经授权核验连续MySQL行日志，补齐31笔已完成订单的35个商品项快照；29项买家评价资格通过API验证，非买家角色限制保留。见[历史归属核验记录](../docs/sdd/evidence/2026-10-21-engagement/historical-review-activation.md)。

2026-10-21本地启用：经用户单独授权，MySQL完整备份及隔离恢复校验通过，咨询／评价两份迁移已应用，8000已重启，25项只读检查通过。见[启用记录](../docs/sdd/evidence/2026-10-21-engagement/local-activation.md)。此前未迁移表述记录的是交付时状态。

当前版本号同步日期：2026-10-21。版本以 `modules.json` 为准；核对状态保留各模块原说明，本次咨询与评价的业务库尚未迁移。

| 模块 | 当前版本 | 当前核对状态 | 完整变更记录 |
| --- | --- | --- | --- |
| core · 项目核心 | 0.9.0 | 请求级MCP契约、独立SDK及固定后端桥接、隔离验收工具。 | [core](changelogs/core.md) |
| users · 用户与权限 | 0.4.2 | 统一登录与权限分流、平台联合鉴权、会话权限、品牌与旧入口清理 | [users](changelogs/users.md) |
| goods · 商品管理 | 0.6.3 | 有购买／评价记录的商品或商品系列删除返回409并提示下架，配合订单历史保护。 | [goods](changelogs/goods.md) |
| carts · 购物车 | 0.2.1 | 保持采购车及商品图片基线；本轮仅web调整币种展示 | [carts](changelogs/carts.md) |
| orders · 订单管理 | 0.4.3 | 库存预留及本人订单能力；列表增加匿名客服定位引用，保留身份与隐藏过滤；本轮无Migration | [orders](changelogs/orders.md) |
| pays · 支付 | 0.2.1 | 保持已有支付基线；验签、金额与回调幂等仍待专项完善 | [pays](changelogs/pays.md) |
| news · 内容资讯 | 0.1.2 | 移除空后台注册文件；资讯API保持原有规则 | [news](changelogs/news.md) |
| inventory · 库存管理 | 0.2.1 | 移除无效导入；库存行为保持原有规则 | [inventory](changelogs/inventory.md) |
| logistics · 物流 | 0.1.1 | 移除无效导入；物流查询和服务保持原有规则 | [logistics](changelogs/logistics.md) |
| supplier · 商家与结算 | 0.4.2 | 禁止物理删除已完成订单，保留买家评价依据；咨询／评价管理导航由web提供。 | [supplier](changelogs/supplier.md) |
| admin_panel · 平台运营 | 0.4.2 | 平台交易总览、角色与权限联合控制、共用销售条件 | [admin_panel](changelogs/admin_panel.md) |
| support_ai · 智能客服 | 0.24.0 | 模型数据入口统一MCP，签名私有上下文、订单交接、偏好依赖和共享预算；隔离验证通过，未重启业务服务或发布。 | [support_ai](changelogs/support_ai.md) |
| merchant_ai · 商家智能助手 | 0.1.0 | 入口与初始化状态，聊天／模型／上传／经营工具未接入 | [merchant_ai](changelogs/merchant_ai.md) |
| ai_storage · AI 记忆与知识存储 | 0.7.1 | 保持查询改写所用知识／向量与短Embedding超时基线 | [ai_storage](changelogs/ai_storage.md) |
| web · 页面与前端资源 | 0.31.9 | 客服方案及金额同步；订单查看按钮定位本人订单，可返回全部，3项脚本VM测试通过，未做浏览器视觉验收 | [web](changelogs/web.md) |
| engagement · 站内咨询与商品评价 | 0.2.2 | 本地咨询与评价已启用；已完成历史商品按日志核验归属后补齐快照，保留角色隔离。 | [engagement](changelogs/engagement.md) |

买家评价仅从“我的订单”的对应商品进入，查看／提交绑定该订单商品；不提供独立“我的评价”导航和跨订单评价列表。

2026-10-22人民币增量：core0.7.0／support_ai0.14.0／web0.29.0／goods0.6.1统一CNY基础金额与共用参考换算，不批量调整业务库金额。见[金额规格](../docs/sdd/architecture/currency.md)。
