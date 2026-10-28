# 全部工作区增量整合与交易履约核对

日期：2026-10-23（Asia/Shanghai）。用户先授权“核对dev，交付全部未合并的工作区内容”，随后明确以主工作区的新预留、幂等下单及可信支付链路为主体，逐项吸收旧工作区商家隔离及状态筛选，单独核对试单／预售。

## 基线、范围及现场保护

- 远端及本地未发现dev分支；实际集成主干为main，交付目标仍为main。审计基线为`eb86abfa136449e08b3efdedbdb74efc16455f08`。
- 盘点6个Worktree，原有各HEAD均已进入main，无未合并的独有提交；剩余产出为主工作区与旧订单修复工作区的未提交增量。使用已有独立工作区的`codex/core-all-workspaces-delivery`保护两处原始现场，未reset、stash、覆盖原工作区或清理仍有工作的目录。
- 主工作区HEAD为`25a08ee29e23ce1bd479951e5860b44c9dfb2a89`，旧订单工作区HEAD为`2d8ccf9fc936ca4efeb36cadb797342d0b16e461`；另外3个干净工作区HEAD为`6ca86d758d3cb30cf98328532205af9b3a9197db`、`f44a811150bbdcad9866989b3c5b700fb778f86e`和`b92cabe19da70484a2ba5acdc91c3f296cde57e1`。整合工作区自身以main为起点。
- 主工作区最初约460个路径（含大量已在main的重复产出）及旧工作区38个路径均逐文件登记，见[归属与去向](workspace-disposition.json)。本轮收口时间为2026-10-23T02:34:44.543150+00:00；整合期间新增的Agent订单只读工具与咨询界面隐藏增量已纳入该冻结快照。
- 原始patch、未跟踪文件字节、冲突预览及本机日志保存在主工作区被忽略的`.scratch/all-workspaces-delivery-20261023/`。原工作区仍可能显示未提交的同一批内容，不代表这些差异未包含于整合分支；未清除原始现场。

## 交易链路决定

1. 结算继续使用服务端价格／Redis已选数量、本人地址、按商家原子拆单、库存预留及幂等编号；创建订单不调用支付渠道。旧结算内立即生成支付链接及其绑定页面由新reservation-checkout替代。
2. 库存账本为有账本商品的唯一可售事实，预留与实物分离；可信付款保持paid预留，取消／到期只释放本订单，发货只消耗本订单已付预留。重复提交／回调／取消／发货均幂等。
3. 归属优先购买时merchant_snapshot，无快照时回退当前商品归属。列表明细和金额仅计本商家商品；混合商家历史订单禁止整单发货／取消，保留待平台处理标记。旧状态筛选和看板统计吸收为子类型感知的过滤。
4. 试单独立校验TrialOrder状态2→3；预售必须定金及尾款均已付，PreSaleOrder状态4→5。仅处理未受管的历史子类型，锁定订单与子记录，不改普通基础status。子记录缺失、付款异常、受管子类型、错误状态或库存不足均拒绝；只能扣未被其他订单预留的可用量。重复发货200且只扣一次，旧报告中的400保留为历史。
5. 原delete接口保留兼容URL，含义改为取消未付款普通订单、释放预留并保留订单记录；已完成订单和试单／预售不能物理删除。界面使用“取消订单”文案，刷新后进入已关闭分类，缺少服务端权限标记时不启用动作。
6. 旧商家隔离、输入校验及回归规则已在lifecycle、supplier列表／动作、checkout_views和新测试中吸收；旧不适用源文件均登记替代去向并保留原始备份。旧验证目录保留，不能用当时的业务库回滚探针作为本次验收。

## 其他纳入功能

纳入主工作区商品发现与分类筛选、收藏商品／商家、商家工作台指标和任务、站内咨询排序／显示／归档、购买评价与昵称相关增量、基础人民币展示一致性，以及Agent可售库存口径和受控只读订单查询。Agent订单事实由Python工具读取，旧order_context不作为实时事实；保留归属、隐藏订单、当前所选绑定、最小字段与查询时间约束。历史咨询在浏览器隐藏，不删除数据库问答。

## 本次验证

配置启动器仅在进程内加载本机配置，命令中的python/node为解释器别名；未把配置凭据写入证据。最终源码指纹见另存的manifest，最终源SHA与同步main SHA在PR正文绑定。

| 命令或覆盖 | 结果 |
| --- | --- |
| `python manage.py check --settings=support_ai.test_settings` | 通过，无系统检查问题 |
| `python manage.py test orders inventory pays carts goods supplier engagement users support_ai --settings=support_ai.test_settings --noinput` | 342项运行，328通过，14项MySQL专用跳过；无失败 |
| `python manage.py test orders.test_reservations supplier.test_order_actions engagement inventory users.test_nickname --settings=engagement.test_mysql_settings --noinput` | 真实随机隔离MySQL库112项通过；库在结束时销毁 |
| `node client/tests/*.test.js`逐文件执行 | 22份文件全部通过，命令未使用shell通配符直接执行 |
| `python client/tests/merchant-orders-contract.py` | 真实合成API→Node、商家范围、子类型、取消保留记录、模板及资源通过 |
| `python client/tests/merchant-overview-contract.py <临时响应JSON>`、`python client/tests/catalog-preview-contract.py <临时响应JSON>`及相应Node测试 | 看板及商品真实响应契约通过 |
| `python client/tests/carousel-contract.py <临时响应JSON>` | 轮播接口、下架／库存过滤与模板通过 |
| 本次定向模板渲染／静态资源脚本 | 19模板编译、15公开页面渲染及34项CSS/JS查找通过；sidebar作为片段而非独立路由 |
| `python -m unittest discover -s tools/tests -p test_git_policy.py -v` | 23项通过 |
| `python -m unittest tools.tests.test_project_identity tools.tests.test_module_versions -v` | 6项通过；历史迁移原文不变 |
| `python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings` | No changes detected |

新增`engagement.0002`、`goods.0011`、`inventory.0002`、`orders.0004`在上述真实隔离MySQL库成功迁移。没有执行业务库Migration，没有自动回退业务库。

初次整合发现旧测试对重复发货400、物理删除订单、USD默认展示及旧Agent字段／调用次数的预期与已选择链路冲突。已按现行契约更新断言，并保留／补充数量只扣一次、流水一次、混合单不变、部分付款拒绝、子类型不占他单预留、购买快照归属、采购车脏输入、Agent实时状态与隐私、不可访问订单统一404等验证。测试替身不调用真实模型或支付服务。

## 版本及历史证据

core 0.8.0、web 0.31.3、orders 0.4.0、inventory 0.2.1、pays 0.2.1、carts 0.2.1、goods 0.6.3、supplier 0.4.0、engagement 0.2.2、users 0.4.2、support_ai 0.17.3。原有main、主工作区及旧工作区changelog条目均保留，不覆盖同版本不同历史说明；最新版本置顶。

少量待交付历史报告包含本机旧物理目录名，公开副本仅将绝对机器路径替为可移植占位符，测试结果和时间不变；原字节与SHA256保留，见[path-normalizations.json](path-normalizations.json)。其他历史证据冲突优先保留main已有结果，并在逐文件归属中说明，未改写失败记录冒充本次通过。

## 未执行及启用边界

未执行真实模型评测、支付／退款渠道联调、业务库回放、全站浏览器视觉验收、部署或PR合入。预留链路上线仍需业务库数据核对及限定迁移、支付商户配置核验和到期清理进程启用的独立授权；试单／预售完整买家付款及后续签收流程仍属于原能力边界，不能从发货兼容推导已完成全闭环。

推送前仍以最终提交执行`python tools/git_policy.py verify --base origin/main`并正常merge最新main；最终执行结果和远端CI以本PR为准。

Delivery-format note: duplicate carriage returns from portable path conversion were normalized. Original bytes and hashes remain in the local backup; recorded test statuses and historical conclusions are unchanged.

Final snapshot also includes preference-storage error classification and one retry of a known broken read connection, plus frontend failure/retry status handling. Four synthetic contracts cover reconnect-once, no retry on configuration faults, stop after a second failure, and no reconnect inside transactions. No live PostgreSQL fault injection was performed.
