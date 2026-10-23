# 购买后商品评价与评分

日期：2026-10-21。能力 CAP-CAT-005，功能 FEAT-038；业务归 MOD-CAT，交易完成事实引用 MOD-TRD，商家回复引用 MOD-MER，治理身份引用 MOD-IAM。实现模块 engagement／orders，页面归 web；goods／supplier 配套保护历史删除。依据本轮用户确认的方案实施。

## 可评价规则

| 类型 | 完成判据 |
| --- | --- |
| standard | OrderInfo.status=4 |
| trial | TrialOrder.status=8；试用中4、试用完成5、退货6／7不视为最终完成 |
| presale | PreSaleOrder.status=6 且 deposit_paid、balance_paid 均为真 |

评价只允许活跃买家评价本人的已完成订单商品。规则读取对应订单类型的真实状态，不混用标准单status；本次不扩展试单试用流程、预售尾款或其他交易生命周期接口。未来退款规则变更须单独设计，不自动删除历史评价或更改评分。

每个 OrderGoods 一条主评价，数量不增加评价次数；再次购买产生新订单商品，可再评价。星级1～5整数，文字去除首尾空白后5～1000字，均必填。无自动好评、空白评论或按金额加权；不提供编辑、追评及晒图。重复完全相同提交重放200；已评价后换内容返回409。

新订单商品保存 merchant_snapshot 与 purchase_snapshot（origin=purchase、商品系列／规格ID、购买时商品名／规格名／商家名和ID），在当前创建订单商品路径调用 save 时写入。历史迁移不批量推断旧商家；旧记录缺少快照返回 HISTORY_NOT_VERIFIED。经明确授权，可用连续完整行日志还原订单商品写入时的SKU／SPU／商家，并与结算等记录核对后定向补齐；必须先备份并在隔离恢复库验证，附带可追溯核验元数据，禁止仅按当前商家猜测。2026-10-21本地已核验并补齐31笔已完成订单的35个商品项，非买家角色限制保留；1笔缺商品行的早期订单未补造，见[核验与启用记录](../../evidence/2026-10-21-engagement/historical-review-activation.md)。未来 bulk_create 新订单商品必须显式提供等价快照，不能绕过归属记录。

## 页面

- 2026-10-22按用户明确要求分流：商品详情“联系商家”进入私聊；订单商品操作区只提供“评价商品／查看评价”，不再显示“联系商家”或消息中心兜底。待付款订单不显示评价入口。
- 买家评价入口归属“我的订单”：每个订单商品通过 can_review、review_id 显示“评价商品”或“查看评价”；保留订单页“待评价”筛选，不设独立“我的评价”导航。
- buyer_reviews.html 是订单商品评价明细，必须携带 order_item_id；未指定有效商品项时返回我的订单。只展示本人选定订单商品及其评价、星级、商家回复与公开状态，不展示其他订单评价或全局评价切换／搜索，不提供私聊入口。提交后在当前明细显示已保存评价，可返回我的订单。历史缺快照的已完成商品只提示暂不可评价，不混入咨询说明。
- 商品详情页评价标签为同页锚点。下方显示一位小数平均分、评价条数、1～5星分布，每条脱敏昵称、星级、购买规格、日期、正文和商家回复。
- 默认同一 merchant+SPU 汇总各规格，可筛选当前SKU；默认最新，也可按评分升／降序，ID作稳定次序。不同商家同名商品不合并，商品转移归属不会把原商家评价带给新商家。无评价时均值为null，显示“暂无评价”。平均分按十进制四舍五入到一位。
- 商家工作台“商品评价”查看本店评价，按星级／商品／内容／未回复筛选，每条公开评价可回复一次，1～1000字纯文本。重复同文重放，不允许改评分、改买家正文或自行隐藏。
- 买家与所属商家可举报，原因5～500字，同一账号同一评价一份举报。举报不自动隐藏差评。
- admin_reviews.html 由活跃平台角色且有 goods_manage 权限者查看举报、隐藏／恢复；每次状态变化保存操作者、前后状态、原因和时间。被隐藏评价在双方本人管理页保留，公开列表与评分排除。

## 数据与接口

Review 一对一关联订单商品，保护买家、购买快照商家、SKU、SPU引用，保存快照、星级、文字、是否公开和时间。数据库约束星级范围与唯一购买项。ReviewReply 一对一关联评价；ReviewReport 对 reporter+review 唯一；ReviewModeration 保存追加式处理记录。

前缀 `/v1/engagement/`。统一响应与认证见[咨询规格](../merchant-operations/buyer-merchant-conversations.md)。评价与回复输出均为纯文本，公开DTO不包含订单号、买家ID、账号全名、联系方式或地址。

| 方法与路径 | 契约 |
| --- | --- |
| GET reviewable-items | 本人订单商品，每页20条；pending=1、order_id、order_item_id可筛选；输出can_review、review_reason、review_id和快照 |
| POST reviews | order_item_id、rating、text；本人完成状态与可信快照校验，首次201、相同重放200 |
| GET products/{sku}/reviews | 公开；scope=all／sku，sort=latest／rating_asc／rating_desc，page；items、summary（total／average／distribution）与分页 |
| GET reviews/mine | 买家本人或商家本店，order_item_id、rating、sku_id、q、unreplied=1、page；先限定买家本人／商家本店，再按订单商品筛选；包含is_visible |
| POST reviews/{id}/reply | 所属商家，一条回复；隐藏评价拒绝409 |
| POST reviews/{id}/report | 活跃买家或评价所属商家，reason；首次201、重复200 |
| GET moderation | 平台+goods_manage；reported=1、rating、q、page；举报和最近处理记录 |
| POST moderation/{id} | 平台+goods_manage，is_visible布尔、reason；记录实际状态变化并同步统计 |

前端 can_review 只控制展示，提交服务端重新检查。提交事务先锁订单、再锁订单商品和SPU；同一购买项唯一评价。汇总以公开Review事实为准，锁SPU后同步原有SKU.comments／SPU.comments；不信任旧计数作为评价存在证据。本次不改变推荐排序。

## 历史保护与迁移

- orders 新增 buyer_hidden，买家隐藏待付款标准单／已完成订单只隐藏本人列表，保留订单商品和公开评价。
- 商家不再物理删除已完成订单，返回409说明需要保留交易和评价依据。该配套限制防止买家评价前交易凭据被删除；不涉及其他分支中的拆单／发货修复。
- 订单商品到SKU改为PROTECT；有交易或评价的商品／系列删除返回409，提示下架。Review到订单商品等引用也为PROTECT。已有业务数据不批量修改、不生成模拟评价。
- 新迁移 orders/0003_auto_20261021_1530.py、engagement/0001_initial.py；历史Migration不修改。
- 业务环境须先备份、单独授权执行迁移，再更新服务。2026-10-21经用户单独授权，当前本地MySQL已备份并应用两份新迁移，8000服务已重启，25项只读检查通过；见[本地启用记录](../../evidence/2026-10-21-engagement/local-activation.md)。未远端部署；历史订单快照不自动补写。

## 验收

本人／他人、活跃／停用、三种订单各阶段、未付尾款、旧快照、商品改名和转店、重复／并发评价、各规格汇总、四舍五入、回复归属和重复、举报幂等、平台权限、隐藏／恢复统计、订单隐藏及商品删除保护、中英阿三语、RTL和手机布局。证据见[验证记录](../../evidence/2026-10-21-engagement/verification.md)。
