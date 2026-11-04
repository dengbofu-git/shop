# tea_saas当前模块版本清单

2026-11-04本地启用：orders0.9.0／pays0.3.0／web0.39.0已在授权备份实恢复后应用pays.0001，原75业务表内容保持，最终09:32:56恢复唯一Web／MCP／清理，知识Worker同源同库。实际接口及迁移就绪通过；支付宝收款方配置仍缺失，真实扣款、退款及商家分账未验收或实现。见[启用记录](../docs/sdd/evidence/2026-11-03-combined-payment/activation.md)。下方记录保留原时点，未提交推送或发布生产。

2026-11-03合并付款增量：orders0.9.0／pays0.3.0／web0.39.0，增加固定付款单、商家分摊与统一收据，买家一次付款、商家独立履约；退款和真实分账另行实施。pays.0001仅隔离验证，尚未应用业务库或重启启用，当前运行版本保持；见[设计](../docs/sdd/modules/trade/combined-payment.md)与[验证](../docs/sdd/evidence/2026-11-03-combined-payment/verification.md)。
2026-11-03商家销售统计说明修正：orders0.8.1／supplier0.4.7／web0.38.1，保留CNY财务资格，增加真实排除数与暂无可统计状态，修正历史订单全NULL时财务全零造成的误解；不修改历史币种或金额，不新增迁移。55项后端及133项前端通过；23:05:07唯一后端已加载，实际94笔排除提示及历史数据保持核验通过，见[启用记录](../docs/sdd/evidence/2026-11-03-merchant-sales-scope/activation.md)。

2026-11-03结算组风控增量：core0.18.0／orders0.8.0／web0.38.0，保留商家独立订单，将逐店累计时长和3笔子单限制替换为3个有效待付结算组，分型释放事件与固定冷却落库。新orders.0008已于22:21:56在授权备份实恢复后应用，唯一后端及清理进程已重启，实际GET确认20种／900秒／3组；见[本地启用](../docs/sdd/evidence/2026-11-03-checkout-groups/activation.md)。下方20:58等记录保留原时点；见[新规格](../docs/sdd/modules/trade/stock-reservations.md)和[本轮证据](../docs/sdd/evidence/2026-11-03-checkout-groups/verification.md)。

2026-11-03 20:58（Asia/Shanghai）已按用户授权重启本地唯一后端：core0.17.0／orders0.7.0／carts0.4.1／web0.37.0／users0.4.4随同Web、MCP、到期进程及知识Worker加载；实际接口确认20种与900秒、旧策略及旧截止不变，见[启用记录](../docs/sdd/evidence/2026-11-03-checkout-light/activation.md)。下方原“未启用”通知保留各次交付时点；仍未提交、推送或发布生产。

2026-11-03轻量结算增量：orders0.7.0／carts0.4.1／web0.37.0／core0.17.0，默认20种实际SKU、平台新普通单固定900秒，原1800秒预算保持；已有登录Hash及外部未付款反馈增量保留。仅本地实现与隔离验证，未启用服务或提交推送，见[本轮证据](../docs/sdd/evidence/2026-11-03-checkout-light/verification.md)。以下日期通知保留原时点含义。

2026-11-03登录采购车计数修复：users0.4.4／core0.16.1，按Hash字段数返回SKU条目数，Redis故障仍允许登录并发出安全固定事件；仅本地源码，未重启启用或提交推送。见[定向验收](../docs/sdd/evidence/2026-11-03-login-cart-hash/verification.md)。

2026-11-03 PostgreSQL完全替换：正式配置拒绝legacy，旧源驱动／测试启动器／源导出入口已退役。旧项目库67表7,005行经备份实际恢复及内容核验后清空，重启后仍为0行，其他库不写入。PG／Redis隔离业务744项中737通过、7项专用数据库测试另批全部通过；原生MCP19项、前端111项通过，四类本地进程统一启用。详见[独立性验收](../docs/sdd/evidence/2026-11-03-postgresql-independence/verification.md)。本次增量未提交／推送，web0.36.3为保留的独立未提交改动。

2026-11-02数据库统一：core0.15.0、ai_storage0.8.0及相关模块已本地使用单一PostgreSQL/default；73表迁移、7,183行内容及65个序列核对、原生备份实恢复、735项PG＋Redis回归见[迁移证据](../docs/sdd/evidence/2026-11-02-postgresql-unification/verification.md)。Git交付状态按本次PR记录。旧日期版本/迁移过程说明保留过程含义，以本段及modules.json为准。

2026-11-02高优先级收口：support_ai0.32.3、web0.36.2、core0.14.0已统一应用本机Web/MCP/知识Worker；orders.0007已备份并完成同版本恢复验证后应用。当前验收、真实支付/模型限制及交付状态以[收口证据](../docs/sdd/evidence/2026-11-02-priority-activation/verification.md)和对应PR收据为准。以下过程记录保留原时点，不表示当前仍未启用。

2026-11-02依赖升级：core0.14.0／support_ai0.31.0采用LangChain1.3.18配套栈，本机后端与MCP已加载；独立及实际运行环境的Agent隔离回归各336项（328通过、8跳过）。未提交/推送，知识Worker镜像未重建，详见[升级证据](../docs/sdd/evidence/2026-11-02-langchain13/verification.md)。

2026-11-02交付后：此前版本已推送MR31（未合入），后续可见历史菜单的本地增量将web升至0.36.2，未再次推送/启用；见[交付及后续证据](../docs/sdd/evidence/2026-11-02-post-pr/verification.md)。

2026-11-02增量：support_ai0.30.1、web0.36.1，R03默认匹配优先与R08恢复错误反馈修复；定向后端103项、前端107项通过。未提交或启用，见[后续证据](../docs/sdd/evidence/2026-11-02-rule-followup/verification.md)。

2026-10-21历史评价启用：经授权核验连续数据库行日志，补齐31笔已完成订单的35个商品项快照；29项买家评价资格通过API验证，非买家角色限制保留。见[历史归属核验记录](../docs/sdd/evidence/2026-10-21-engagement/historical-review-activation.md)。

2026-10-21本地启用：经用户单独授权，当时数据库完整备份及隔离恢复校验通过，咨询／评价两份迁移已应用，8000已重启，25项只读检查通过。见[启用记录](../docs/sdd/evidence/2026-10-21-engagement/local-activation.md)。此前未迁移表述记录的是交付时状态。

当前版本号同步日期：2026-11-03。版本以 `modules.json` 为准；R01/R02、R05/R06/R08/R09源码已本地启用，orders.0007已应用本地业务库。提交/推送收据单列，未合入或部署生产。

| 模块 | 当前版本 | 当前核对状态 | 完整变更记录 |
| --- | --- | --- | --- |
| core · 项目核心 | 0.18.0 | 结算组／冷却配置和迁移预检已在本机加载，唯一运行源及PG健康核验通过。 | [core](changelogs/core.md) |
| users · 用户与权限 | 0.4.4 | 登录Hash计数修复随最新版加载，Redis故障降级保留；无真实账号登录写入验收。 | [users](changelogs/users.md) |
| goods · 商品管理 | 0.7.6 | 种子命令使用PG库名及集群身份守卫；导入并发在PG通过。 | [goods](changelogs/goods.md) |
| carts · 购物车 | 0.4.1 | 快照在写入前复核本次选择上限；已有消费游标、故障重试及新加购保留均回归通过。 | [carts](changelogs/carts.md) |
| orders · 订单管理 | 0.9.0 | 合并付款生命周期协调已本机启用；0008既有规则与原业务数据保持。 | [orders](changelogs/orders.md) |
| pays · 支付 | 0.3.0 | 固定付款单、分摊和收据已迁移启用；真实扣款因收款方配置缺失不可用，退款／分账另行实施。 | [pays](changelogs/pays.md) |
| news · 内容资讯 | 0.1.2 | 移除空后台注册文件；资讯API保持原有规则 | [news](changelogs/news.md) |
| inventory · 库存管理 | 0.2.2 | 通用库存/仓库限定有效平台角色和显式权限；商家保留本店库存接口，已本地启用。 | [inventory](changelogs/inventory.md) |
| logistics · 物流 | 0.1.2 | 本人买家、本店完整订单或平台显式权限读取物流；拒绝跨账号及商家混合单，已本地启用。 | [logistics](changelogs/logistics.md) |
| supplier · 商家与结算 | 0.4.7 | 同店销售币种覆盖计数已本机加载，实际94笔历史未知币种排除数通过，原数据不回填。 | [supplier](changelogs/supplier.md) |
| admin_panel · 平台运营 | 0.4.3 | CNY财务汇总排除历史未知和其他币种，保留订单数及角色/权限控制，已本地启用。 | [admin_panel](changelogs/admin_panel.md) |
| support_ai · 智能客服 | 0.32.5 | 评测工具使用PG身份守卫；业务与常驻MCP统一default，真实模型评测未执行。 | [support_ai](changelogs/support_ai.md) |
| ai_storage · AI 记忆与知识存储 | 0.8.1 | 单default事务、向量及7项专用OCR/视觉数据库测试在PG通过，Worker仅连接统一PostgreSQL。 | [ai_storage](changelogs/ai_storage.md) |
| web · 页面与前端资源 | 0.39.0 | 合并付款入口和权威待付金额已本机加载；保留简洁提交文案，未发布生产。 | [web](changelogs/web.md) |
| engagement · 站内咨询与商品评价 | 0.2.5 | 咨询／评价及并发在PG通过，旧源测试启动器移除。 | [engagement](changelogs/engagement.md) |

买家评价仅从“我的订单”的对应商品进入，查看／提交绑定该订单商品；不提供独立“我的评价”导航和跨订单评价列表。

2026-10-22人民币增量：core0.7.0／support_ai0.14.0／web0.29.0／goods0.6.1统一CNY基础金额与共用参考换算，不批量调整业务库金额。见[金额规格](../docs/sdd/architecture/currency.md)。
