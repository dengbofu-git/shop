# 库存预留、订单取消与批量采购

规格0.6.0，2026-11-03，执行R04/R07。新增[合并付款规格](combined-payment.md)：独立付款单协调同组待付子单，保留商家独立履约，退款另行实施；新pays.0001已于2026-11-04经授权备份实恢复后应用本机，原业务表数据保持并统一重启，见[合并付款启用](../../evidence/2026-11-03-combined-payment/activation.md)。当前批准增量以最多3个有效待付结算组及分类型释放风控，替换1800秒逐子单预算、3个子单上限和取消／超时混合计次，见[ADR0015](../../../adr/0015-checkout-group-risk.md)。新orders.0008_checkout_risk已于22:21:56经用户授权，备份实恢复后应用并重启本机唯一后端及清理进程；原业务数据保持，见[本地启用](../../evidence/2026-11-03-checkout-groups/activation.md)。启动预检继续拒绝缺迁移的重启，不自动迁移。

此前INV-CHECKOUT-LIGHT-20261103的20种SKU上限、平台900秒和账本锁前额度检查保持。其[ADR0014](../../../adr/0014-light-checkout-reservations.md)、[隔离验收](../../evidence/2026-11-03-checkout-light/verification.md)及20:58[本地启用证据](../../evidence/2026-11-03-checkout-light/activation.md)按原时点保留；此前启用不代表本次结算组风控已生效。

历史记录：2026-10-29补充采购车清理任务的事务和重试设计。orders.0006已获单独授权并在本地备份后启用，63张原业务表摘要不变；原预留、防占用、取消／隐藏及历史子类型发货的既有启用记录保留。见[统一复核及启用证据](../../evidence/2026-10-29-local-unification/verification.md)。

本地启用记录：2026-10-26获用户单独授权，备份后应用inventory.0002、orders.0004/0005；原业务列数据核验不变，后端及30秒到期清理进程已启动。支付收款方ID当前缺失，支付链接仍按保护规则拒绝生成；未进行真实支付。详见[启用证据](../../evidence/2026-10-26-stock-reservations/activation.md)，本记录不代表生产部署或开机自启已配置。

## 库存和支付不变量

- 采购车是意向清单，不预留。下单按有效本人身份、本人地址、服务端价格、Redis已选数量、上架及商家状态重新检查。
- 有账本时仅启用仓可用量为可售事实，禁止取max(账本,SKU.stock)；无账本首次结算在SKU锁内初始化默认仓，SKU.stock仅作实物投影。
- 每仓quantity>=0、0<=reserved_quantity<=quantity、available_quantity=quantity-reserved_quantity。商家调整不能低于预留，多仓不能由一个总数覆盖。
- 同结算按商家原子拆单，任一商品失败全部回滚并保留采购车。每个预留绑定订单商品与仓库，reserved/paid/consumed/released可追踪。
- 单次默认最多20种不同SKU，按后端归一化实际集合计数，不按总件数或客户端声称的行数；上限内不按小批事务分段提交，超限由买家减少勾选后另行结算。重复SKU继续拒绝，不合并数量。
- 锁顺序为买家→关联付款单→升序订单→升序SKU→升序账本／预留；重复下单、回调、取消、到期及发货均幂等。

结算种类上限在到期兜底扫描之前检查，因为扫描也会取得库存锁。总数量在SKU锁前检查，其余不依赖库存的价格／有效待付结算组数／金额／店铺额度／同SKU重复预留在首次账本锁前检查；库存与占比最终以锁内状态复核。`locked_ledgers`的联表锁继续保护仓库is_active，未盲目移除仓库关联锁。固定顺序与有界规模不构成FIFO、无等待或无死锁保证；数据库冲突回滚后，HTTP返回CHECKOUT_BUSY，须使用原请求编号重试。

数据库锁只在事务中持有，事务提交或回滚后释放；待付款900秒保留的是预留记录，不是900秒数据库锁。普通MVCC快照查询与竞争更新锁分别理解。

| 事件 | 标准订单状态 | 实物 | 预留 | 可售 |
| --- | --- | --- | --- | --- |
| 下单N件 | 待付款1 | 不变 | +N | -N |
| 可信付款 | 待发货2 | 不变 | 保留并转paid | 不变 |
| 取消或到期 | 已关闭0 | 不变 | 释放本单N | +N |
| 发货 | 待收货3 | -N | 消耗本单N | 不变 |

已付款预留不超时释放。异步POST须验签、app_id、seller_id、金额、交易状态及唯一trade_no；GET跳转不确认付款。付款与取消以买家和付款单／订单锁协调；旧单已关闭后可信到账记录late_payment_refund_required，合并付款失效或迟到到账登记review并关闭其余未付占用，库存不复活、不自动退款。历史订单不能自动补造可信支付或预留；异常通知记legacy_payment_review。ALIPAY_SELLER_ID及应用私钥、支付公钥、应用ID、通知地址和网关均须正确配置，收款方缺失不生成支付链接；本规则不证明真实渠道联调完成。

## 取消与隐藏（R04）

未付款普通订单只提供“取消订单”，关闭并释放一次；已付订单不能取消释放。关闭或完成的订单可“隐藏订单”，只设置本人列表可见性，不改变状态、库存、评价或交易证据。待付款不提供隐藏入口，服务端拒绝以隐藏操作隐式取消；旧delete URL如保留，仅按上述隐藏状态检查，不物理删除交易记录。

商家兼容delete路由表达“取消未付款普通订单并保留记录”，不能删除已完成或子类型订单。UI按服务端能力标记展示，缺标记不启用动作。本人隐藏、商家取消和管理员处理必须明确操作者与作用范围。

## 普通在线采购与试运行风控（R07）

| 配置 | 当前试运行默认 |
| --- | --- |
| 单次结算SKU种类 | RESERVATION_MAX_SKUS_PER_CHECKOUT默认20，可由受控服务端配置；多件同SKU仍算1种 |
| 普通在线预留期限 | 平台固定900秒（15分钟），不由店铺历史TTL覆盖；截止不因刷新／重试延长 |
| 店铺待付数量／金额／库存占比 | 100件／20000元／50%，店铺可在已定义边界内配置，占比1—100% |
| 平台账号有效待付结算组 | 最多3组；同一次CheckoutRequest跨店拆单仍算1组 |
| 平台账号累计待付数量／金额 | 300件／60000元；跨组、跨店按真实数量金额累计 |
| 账号成功结算频率 | 每分钟5次 |
| 未付超时冷却 | 最近1小时至少3个不同结算组发生真实超时释放，触发固定30分钟 |
| 买家取消冷却 | 最近1小时至少5个不同结算组发生真实买家取消释放，首次固定10分钟；距上次取消冷却触发不足24小时再次触发为30分钟 |
| 来源新尝试 | 每分钟30次，服务端IP HMAC，失败也计，幂等重放不新增 |

同买家同SKU不得跨结算组重复预留。一个有效待付组要求存在归属该买家的受管、未付款、未过截止订单，且仍有state=reserved的StockHold；同CheckoutRequest只计1组。旧受管订单checkout_request_id为NULL时，每个实际有效占用订单分别计1组，不补造关联、不合并历史记录。未受管或没有reserved占用的旧订单不计组名额；既有数量／金额兼容统计仍保留，不能借此豁免原账号或店铺额度。

组内部分商家订单付款或取消后，只要还有有效未付预留，仍计1组；最后一份未付占用付款、取消或到期后释放组名额。释放名额不释放已付款paid预留。每商家仍有独立订单、购买商家快照、金额及取消入口；买家付款入口按同次结算汇总有效待付子单，历史无checkout关联订单仍走原单付款；一次结算的所有新订单共享同一个900秒截止，3个以上商家在SKU和其他原额度允许时仍可一次结算。

组准入和原子创建在同一买家锁事务内检查，付款、关闭也按买家→关联付款单→升序订单→SKU→账本顺序协调；两个请求竞争最后1组最多1个创建成功。达到3组返回HTTP429、UNPAID_CHECKOUT_LIMIT，携带pending_checkout_groups=3和max_unpaid_checkouts=3。任一库存、数量、金额或后续写入失败，整次CheckoutRequest、每店订单、明细、预留和采购车清理任务全部回滚；已持久化的风控事实及固定冷却不因准入拒绝而丢失。相同请求编号同意图回放原结果，不新增组或续期；异意图仍拒绝。

不再累计1800秒预留时长，也不按商家子单数量限制为3。旧订单继续按自身原截止到期及幂等回放，不追溯延长。RESERVATION_MAX_UNPAID_CHECKOUTS默认3；原RESERVATION_MAX_UNPAID_ORDERS与RESERVATION_MAX_HOLD_SECONDS_PER_HOUR不再参与准入。SKU、数量／金额和来源限制仍由RESERVATION_MAX_SKUS_PER_CHECKOUT、RESERVATION_MAX_UNPAID_QUANTITY、RESERVATION_MAX_UNPAID_AMOUNT、RESERVATION_IP_REQUESTS_PER_MINUTE受控配置；店铺额度及占比不变。额度、账号、风控和来源窗口由PostgreSQL锁保护，Redis不是额度事实源。

风控事件只根据受管订单真实StockHold释放记录。以买家、结算组、事件类型去重，同组多个子单的同类释放仅计1次；同组分别发生取消和超时可各有1条事实，两个类型独立判断，不将1次取消和2次超时混成3次超时。商家取消、重复关闭、隐藏订单、无真实释放及已付款占用不产生买家取消／超时罚点。旧NULL关联按订单分别建组键。

ReservationRiskEvent持久记录事实，ReservationRiskState保存分类型已消费事件游标、cooldown_until、原因及上次取消冷却触发时刻。最近1小时的新事件达阈值时消费该类本轮事件并固定截止，超时优先；冷却期间刷新／重试返回同一截止及向上取整的剩余秒数，不延长。届满不因同一批旧事件立即重复触发；新事件仍需满足新一轮阈值。首次取消冷却10分钟，24小时内再次触发30分钟，达到24小时后回到10分钟。响应为HTTP429、RESERVATION_COOLDOWN，包含retry_after、cooldown_until和cooldown_reason（timeout或cancel）。参数由RESERVATION_TIMEOUT_GROUPS_PER_HOUR／RESERVATION_TIMEOUT_COOLDOWN_SECONDS、RESERVATION_CANCEL_GROUPS_PER_HOUR／RESERVATION_CANCEL_COOLDOWN_SECONDS、RESERVATION_REPEAT_CANCEL_COOLDOWN_SECONDS及RESERVATION_CANCEL_ESCALATION_WINDOW_SECONDS受控配置。

`orders/reservation_policy.py`提供不可变有效策略快照，ttl_source=platform_fixed_900_v1。数据库`ReservationPolicy.ttl_seconds`及旧600默认仅作为历史配置兼容保留，不作为新普通单期限来源；数量／金额／占比仍取店铺原配置。GET同时返回有效ttl_seconds=900、configured_ttl_seconds、ttl_editable=false；无记录GET不建行。不需要仅为改默认而新增Migration，也不批量覆盖现有策略或伪造商家审计。

以上是试运行参数，不构成所有商家、包装单位和批量采购的统一业务上限。每次变更记录操作者、值、依据及生效时间，只影响新预留；商家限本店配置，平台总额／频控由管理员受控配置，不能由客户端或模型覆盖。不自动提高当前上限，不清零滥用历史，不信任任意转发头。

超出在线阈值返回BULK_CONFIRMATION_REQUIRED，保留采购内容并引导商品详情联系商家，说明尚未形成可付款订单。商家确认批量供货后仍需可靠报价、时限和可售库存核验；当前不承诺已实现报价单、授信、自动豁免、企业认证或定金流程，不偷偷拆单绕过限额。

## 商家隔离及历史子类型

归属优先购买时商家快照，无快照回退商品归属。历史混合商家单拒绝整单发货／取消，列表金额仅计本店明细。

未受管试单独立校验TrialOrder状态2→3；预售须定金、尾款均已付且PreSaleOrder状态4→5。不修改基础status，只消耗未被他单预留的数量；子记录缺失、异常付款、错误状态、受管子类型和库存不足均拒绝。重复发货幂等成功且库存／流水只一次。新标准结算入口不据此开放试单／预售新建、支付或退款全流程。

## 接口与启用

本次orders.0008_checkout_risk新增风控事件及状态表、约束和索引；历史迁移不修改。历史回填仅接受受管已关闭订单、明确user_cancel／expired原因及可信released hold时间链，排除未知、无释放证据和未来时间；按组与类型幂等去重，不重写订单、CheckoutRequest、旧截止、店铺策略或库存。只在隔离PostgreSQL验证；业务库迁移、服务重启及只读核验仍须分别执行并记录。运行启动预检只读检查待应用Migration，发现0008等缺失即阻止重启，不自动执行migrate。

创建POST /v1/orders/<username>要求有效本人买家及16—64位ASCII安全字符幂等编号（Idempotency-Key或request_id）；同编号同意图回放，改变意图409；返回orders[]，创建不调用支付渠道。采购车清理失败不能撤销已提交订单，也不能只记录日志后永久丢失清理意图。GET advance返回reservation_checkout_version=1，旧后端无标记时页面禁止创建无保护订单。取消仅POST本人/cancel；type=5只为本人有效未过期受管订单发起付款，有checkout关联时转同组付款单，无关联旧单保留原路径；固定截止不延长。

GET advance增加checkout_sku_limit和reservation_ttl_seconds，直接购买算1种；采购车按Redis status为true的实际已选项解析。POST再次检查，sku_list缺省/null/空列表仍表示全部已选，非空列表只是实际已选子集，伪造count/price不能覆盖Redis或服务端事实。超限返回HTTP400、CHECKOUT_SKU_LIMIT、checkout_sku_limit及“单次最多结算20种商品，请减少勾选数量后分批结算”（配置改变时同步数字）；预览和提交均不创建订单／预留／清理任务，不消费采购车或升级旧字段。前端按后端配置校验行数并引导回采购车，已有订单付款不套新上限。

### 采购车清理任务

- Redis条目包含generation、version、added、removed及count；count=added-removed。删除后重加形成新generation，旧任务不能作用于新条目；旧格式在结算快照中受控升级。
- 新请求先只读核对集合；Lua快照在任何HSET前再次计数，覆盖预检查后并发勾选／加购超限。拒绝前不主动执行旧清理任务；若旧消费区间尚未同步，新请求按CART_CHANGED安全拒绝，原请求重放、后台进程或显式重试继续同步，不重复购买旧区间。
- 创建订单在买家锁内，把CheckoutRequest、预留及CartCleanupTask放入同一PostgreSQL/default事务；任务记录本次已购买数量区间。任务写入失败则订单和预留一起回滚。
- 事务提交后尝试清理；Redis Lua只将已处理位置推进到任务截止游标，保留之后新加的数量。Redis已执行但PostgreSQL任务确认失败时可重放，不重复减量；同代同数量区间不能被不同结算请求重复购买。
- 断连时任务保留pending，记录尝试次数、异常类型和有界退避时间；日志不记录采购内容或连接凭据。watch_stock_reservations同时处理到期订单与待清理任务；retry_cart_cleanup支持显式重试，所有任务均使用服务端买家归属。
- 读取采购车不改写数量或删除缺货行；返回available_stock及stock_shortage，页面保留意向数量并提示调整。移除前端固定9件上限，最终下单仍执行现有库存、预留占比、账号额度及防占用限制。
- 本轮新增迁移仅创建清理任务表、约束及索引，不回填或修改历史订单。历史迁移不改写；业务库备份、授权启用和启用后只读核验独立记录。

商家reservation-policy仍要求本店四字段及必填change_reason，ttl_seconds仅可提交900作为平台固定规则确认，实际只修改数量／金额／占比三项，已有历史TTL不回写；新建配置行显式900。依据须为1—200字符，身份、数量、金额和边界在服务端检查。ReservationPolicyChange同事务记录真实商家actor、含有效来源与历史TTL的before/after、reason、effective_at；不冒充商家记录平台切换。结算内使用单份不可变有效策略快照。到期进程watch_stock_reservations每30秒或定时expire_stock_reservations，访问时清理只作兜底。

订单页区分应付与实付，未付款／已关闭不标实付；显示期限、关闭状态及支付异常。

inventory.0002/orders.0004等现有迁移及启用材料见[原预留证据](../../evidence/2026-10-22-stock-reservations/verification.md)；本轮新增orders.0005_reservationpolicychange。历史迁移不可改，业务库须重新核对实际计划，备份后单独授权限定迁移并核验。早期定向验证及其实际组件见[原日期证据](../../evidence/2026-10-26-stock-reservations/verification.md)，覆盖隐藏无副作用、取消／付款竞态、规则审计、批量出口、混合单、试单／预售及他单预留。本轮未调用真实支付／退款。
