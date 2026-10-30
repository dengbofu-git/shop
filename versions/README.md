# tea_saas当前模块版本清单

2026-10-21历史评价启用：经授权核验连续MySQL行日志，补齐31笔已完成订单的35个商品项快照；29项买家评价资格通过API验证，非买家角色限制保留。见[历史归属核验记录](../docs/sdd/evidence/2026-10-21-engagement/historical-review-activation.md)。

2026-10-21本地启用：经用户单独授权，MySQL完整备份及隔离恢复校验通过，咨询／评价两份迁移已应用，8000已重启，25项只读检查通过。见[启用记录](../docs/sdd/evidence/2026-10-21-engagement/local-activation.md)。此前未迁移表述记录的是交付时状态。

当前版本号同步日期：2026-10-29。版本以 `modules.json` 为准；历史启用记录保留原时点，新的本地整合与实际部署、推送分别记录。

| 模块 | 当前版本 | 当前核对状态 | 完整变更记录 |
| --- | --- | --- | --- |
| core · 项目核心 | 0.12.0 | Python3.13/Django5.2、统一启动与快照绑定本地迁移；保留已审核主干和商家助手退役。 | [core](changelogs/core.md) |
| users · 用户与权限 | 0.4.2 | 统一登录与权限分流、平台联合鉴权、会话权限、品牌与旧入口清理 | [users](changelogs/users.md) |
| goods · 商品管理 | 0.7.3 | 保留商品导入与收藏；推荐/采购车统一有效商家、正价和有库存的可售范围。 | [goods](changelogs/goods.md) |
| carts · 购物车 | 0.4.0 | 原子追加及幂等保留；增加生成标识与数量游标，缺货读取不减量，展示商品名和独立规格。 | [carts](changelogs/carts.md) |
| orders · 订单管理 | 0.5.0 | 库存预留及本人订单能力保留；新增同事务采购车清理任务与重试，0006已单独授权并在本地备份后启用。 | [orders](changelogs/orders.md) |
| pays · 支付 | 0.2.1 | 保留可信POST回调验签、商户/金额校验及幂等；真实商户联调、退款与对账仍需专项验收。 | [pays](changelogs/pays.md) |
| news · 内容资讯 | 0.1.2 | 移除空后台注册文件；资讯API保持原有规则 | [news](changelogs/news.md) |
| inventory · 库存管理 | 0.2.1 | 移除无效导入；库存行为保持原有规则 | [inventory](changelogs/inventory.md) |
| logistics · 物流 | 0.1.1 | 移除无效导入；物流查询和服务保持原有规则 | [logistics](changelogs/logistics.md) |
| supplier · 商家与结算 | 0.4.2 | 禁止物理删除已完成订单，保留买家评价依据；咨询／评价管理导航由web提供。 | [supplier](changelogs/supplier.md) |
| admin_panel · 平台运营 | 0.4.2 | 平台交易总览、角色与权限联合控制、共用销售条件 | [admin_panel](changelogs/admin_panel.md) |
| support_ai · 智能客服 | 0.29.0 | 常驻HTTP MCP及SSE与CP-SAT、购买条件证据、可售校验完整整合。 | [support_ai](changelogs/support_ai.md) |
| ai_storage · AI 记忆与知识存储 | 0.7.3 | Worker使用统一当前镜像与Python3.13依赖；OCR／重排序／向量模型及知识文件保持。 | [ai_storage](changelogs/ai_storage.md) |
| web · 页面与前端资源 | 0.35.0 | 流式客服与推荐加车并存；人民币默认、商品标题、缺货提示及采购数量交互统一。 | [web](changelogs/web.md) |
| engagement · 站内咨询与商品评价 | 0.2.3 | 隔离MySQL测试设置兼容Django 5.2；咨询、评价及身份隔离保持原行为。 | [engagement](changelogs/engagement.md) |

买家评价仅从“我的订单”的对应商品进入，查看／提交绑定该订单商品；不提供独立“我的评价”导航和跨订单评价列表。

2026-10-22人民币增量：core0.7.0／support_ai0.14.0／web0.29.0／goods0.6.1统一CNY基础金额与共用参考换算，不批量调整业务库金额。见[金额规格](../docs/sdd/architecture/currency.md)。
