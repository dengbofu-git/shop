# tea_saas当前模块版本清单

2026-11-02依赖升级：core0.14.0／support_ai0.31.0采用LangChain1.3.18配套栈，本机后端与MCP已加载；独立及实际运行环境的Agent隔离回归各336项（328通过、8跳过）。未提交/推送，知识Worker镜像未重建，详见[升级证据](../docs/sdd/evidence/2026-11-02-langchain13/verification.md)。

2026-11-02交付后：此前版本已推送MR31（未合入），后续可见历史菜单的本地增量将web升至0.36.2，未再次推送/启用；见[交付及后续证据](../docs/sdd/evidence/2026-11-02-post-pr/verification.md)。

2026-11-02增量：support_ai0.30.1、web0.36.1，R03默认匹配优先与R08恢复错误反馈修复；定向后端103项、前端107项通过。未提交或启用，见[后续证据](../docs/sdd/evidence/2026-11-02-rule-followup/verification.md)。

2026-10-21历史评价启用：经授权核验连续MySQL行日志，补齐31笔已完成订单的35个商品项快照；29项买家评价资格通过API验证，非买家角色限制保留。见[历史归属核验记录](../docs/sdd/evidence/2026-10-21-engagement/historical-review-activation.md)。

2026-10-21本地启用：经用户单独授权，MySQL完整备份及隔离恢复校验通过，咨询／评价两份迁移已应用，8000已重启，25项只读检查通过。见[启用记录](../docs/sdd/evidence/2026-10-21-engagement/local-activation.md)。此前未迁移表述记录的是交付时状态。

当前版本号同步日期：2026-10-30。版本以 `modules.json` 为准；R01/R02、R05/R06/R08/R09已补源码及隔离证据，尚未提交或启用，orders.0007未应用业务库。历史启用记录保留原时点，实际部署、推送分别记录。

| 模块 | 当前版本 | 当前核对状态 | 完整变更记录 |
| --- | --- | --- | --- |
| core · 项目核心 | 0.14.0 | LangChain1.3配套依赖已锁定并应用本机运行环境；此前统一运行及MCP契约保留。 | [core](changelogs/core.md) |
| users · 用户与权限 | 0.4.2 | 统一登录与权限分流、平台联合鉴权、会话权限、品牌与旧入口清理 | [users](changelogs/users.md) |
| goods · 商品管理 | 0.7.4 | 公开缺货详情可读，推荐/采购车仍要求有效商家、正价和正库存，待启用。 | [goods](changelogs/goods.md) |
| carts · 购物车 | 0.4.0 | 原子追加及幂等保留；增加生成标识与数量游标，缺货读取不减量，展示商品名和独立规格。 | [carts](changelogs/carts.md) |
| orders · 订单管理 | 0.6.0 | 新建CNY快照，历史NULL不推断、不进入CNY财务比较；0007仅隔离验证，原0006启用记录保持。 | [orders](changelogs/orders.md) |
| pays · 支付 | 0.2.2 | 未知或非CNY订单付款需人工核验；保留可信回调验签与幂等，真实渠道仍待专项验收。 | [pays](changelogs/pays.md) |
| news · 内容资讯 | 0.1.2 | 移除空后台注册文件；资讯API保持原有规则 | [news](changelogs/news.md) |
| inventory · 库存管理 | 0.2.2 | 通用库存/仓库限定有效平台角色和显式权限；商家保留本店库存接口，待启用。 | [inventory](changelogs/inventory.md) |
| logistics · 物流 | 0.1.2 | 本人买家、本店完整订单或平台显式权限读取物流；拒绝跨账号及商家混合单，待启用。 | [logistics](changelogs/logistics.md) |
| supplier · 商家与结算 | 0.4.4 | 旧看板无来源指标占位、销售按购买归属和CNY聚合，订单DTO携带币种；待启用。 | [supplier](changelogs/supplier.md) |
| admin_panel · 平台运营 | 0.4.3 | CNY财务汇总排除历史未知和其他币种，保留订单数及角色/权限控制，待启用。 | [admin_panel](changelogs/admin_panel.md) |
| support_ai · 智能客服 | 0.32.1 | 统一PII续补历史/预览协议一致性、无效工具调用及显式联系方式字段；本地验证通过，未推送或统一重启验收。 | [support_ai](changelogs/support_ai.md) |
| ai_storage · AI 记忆与知识存储 | 0.7.3 | Worker使用统一当前镜像与Python3.13依赖；OCR／重排序／向量模型及知识文件保持。 | [ai_storage](changelogs/ai_storage.md) |
| web · 页面与前端资源 | 0.36.2 | MR31含0.36.1；本地续增咨询历史可见菜单按钮及焦点恢复，未再次推送/启用。 | [web](changelogs/web.md) |
| engagement · 站内咨询与商品评价 | 0.2.3 | 隔离MySQL测试设置兼容Django 5.2；咨询、评价及身份隔离保持原行为。 | [engagement](changelogs/engagement.md) |

买家评价仅从“我的订单”的对应商品进入，查看／提交绑定该订单商品；不提供独立“我的评价”导航和跨订单评价列表。

2026-10-22人民币增量：core0.7.0／support_ai0.14.0／web0.29.0／goods0.6.1统一CNY基础金额与共用参考换算，不批量调整业务库金额。见[金额规格](../docs/sdd/architecture/currency.md)。
