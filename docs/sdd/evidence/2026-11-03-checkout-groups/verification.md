# 商家独立订单与结算组风控验收

后续本地启用：2026-11-03 22:21:56（Asia/Shanghai）经用户明确授权，原生备份实恢复后应用0008并重启唯一后端及清理进程；实际20种／900秒／3组接口通过，旧73业务表摘要不变，见[启用记录](activation.md)。下文“未应用／未重启”保留原隔离交付时点，未新增Git或生产发布授权。

日期：2026-11-03（Asia/Shanghai）。用户在确认按商家拆单后要求实施。范围为本地源码、版本、规格和隔离验证；没有业务库迁移、服务重启、Git提交／推送／PR或生产发布授权。

基线HEAD：`a864f909b57ab0a53d213472f6f317b09eb8ee4e`，分支`codex/core-pg-retirement`。既有PG-only、登录Hash、20SKU／900秒和外部未付款恢复增量保留。新版本core0.18.0、orders0.8.0、web0.38.0，其他模块版本保持。依据[实施计划](../../../superpowers/plans/2026-11-03-checkout-group-risk.md)、[规格0.5.0](../../modules/trade/stock-reservations.md)及[ADR0015](../../../adr/0015-checkout-group-risk.md)。

## 最终行为

- 商家仍各有独立订单、金额、购买快照、付款、取消、发货和评价；沿用CheckoutRequest关联一次提交，不产生合并财务订单或合并付款。各店新子单共享固定900秒截止，部分付款和幂等重放不续期。
- 删除1800秒逐店累计预算和3笔子单上限。按真实有效未付reserved hold最多3个结算组；多店一次提交只占1组，部分付款／取消仍有未付占用时继续计1。旧NULL关联受管单各算1组，没有reserved hold的历史单不占名额，原数量金额兼容统计保留。
- 每组默认20种SKU，重复SKU拒绝；全账号300件／CNY60000、店铺数量／金额／实物占比及同SKU已有待付款限制继续跨组生效。创建、预留、清理任务在同一事务全部成功或回滚。
- PostgreSQL持久记录按组同类唯一的真实释放事实。最近1小时3组超时冷却30分钟；5组买家取消后再次提交冷却10分钟，24小时内再次触发取消规则为30分钟。固定截止及已消费事件游标避免刷新续罚和重复处罚。部分付款不免除剩余超时，商家取消及无本次释放不罚买家。
- 风控状态在内部事务正常提交后才由外层抛拒绝；买家锁串行化组准入、付款及关闭。冷却只拒绝新结算，已有订单的付款、取消及原请求回放仍可用。失败来源尝试限流保留。
- 预览返回真实组上限，提交返回组标识、共同截止和各单原购买商家快照。页面分别提供各单付款入口，组数超限和冷却引导处理已有订单，并展示服务端恢复时间。

## 实际环境与命令

独立内部Docker网络，PG16／pgvector0.8.7及Redis7.4.5-alpine均使用tmpfs，无主机端口、持久卷或业务数据挂载。每次将当前跟踪／非忽略源码打包至Linux临时目录，排除私有.env、Git与.scratch；仅合成凭据和不可访问的模型／支付地址。镜像无MySQL驱动，每批使用随机PG测试库，真实多连接测试没有用SQLite替代。

执行器为主目录`.scratch/checkout-groups-20261103/run_tests.py <run> <labels...>`，使用`.scratch/runtime-py313/Scripts/python.exe -X utf8 -B`调用；内部执行Django test，settings为`tea_saas.pg_test_settings`。每批`*-source.json`绑定实际打包源码。

| 阶段 | 实际范围／命令 | 结果 |
| --- | --- | --- |
| 风险RED | `risk-red orders.test_checkout_risk` | 7项按预期失败，缺持久化风险模型 |
| 组RED | `groups-red orders.test_checkout_groups orders.test_checkout_group_concurrency` | 21项中3失败、13错误；旧时长／子单限制拒绝应允许的结算 |
| 首次定向GREEN | `groups-green orders.test_checkout_groups orders.test_checkout_group_concurrency orders.test_checkout_policy orders.test_reservations orders.test_checkout_risk` | 64项通过，5.134秒 |
| 独立审查边界RED | `stale-release-red orders.test_checkout_risk_integration.CheckoutRiskIntegrationTests.test_stale_released_holds_without_a_new_release_never_create_penalties` | 1项的取消／超时两个子例失败，复现无本次释放仍记罚点 |
| 最终PG／Redis集成 | `verified-final orders inventory pays carts goods supplier engagement users support_ai ai_storage logistics tea_saas.test_runtime_logging` | **848项：841通过，7项专用OCR／视觉数据库测试跳过**，40.265秒，退出0 |
| 前端 | 枚举`client/tests/*.test.js`完整路径后执行`node --test @testFiles` | **125/125通过**，0跳过，573.365毫秒 |
| 工具治理 | `python -B -m unittest discover -s tools/tests -v` | **97项：96通过，1项Windows符号链接权限跳过**，39.612秒 |
| 迁移／启动预检 | `run_checks.py readiness ignored` | 隔离库仅到0007时，正式backend.py --check拒绝且明确列出0008；隔离应用后预检通过。没有启动服务 |
| 模型与模板 | 同一readiness批次调用makemigrations --check --dry-run及模板loader | No changes detected；payment／gopay／merchant_inventory／orderConfirm四页面渲染通过 |
| Git策略与范围 | 临时index执行`python tools/git_policy.py verify`；`git diff --check` | 125个当前变更文件、15模块归属、62项Python／JS语法通过；真实index未改，历史迁移未改 |

首次阶段集成`integration`为845项、1失败和6错误，未计为通过：并发测试误将线程编号当作PG队列顺序；旧货币迁移测试清理时固定恢复0007，导致后续缺风险表。分别改为递归验证两个请求的真实阻塞链，以及恢复测试开始时的实际迁移叶节点。随后`integration-final`847项通过（7跳过），再加入独立审查的真实释放修复与新增回归，形成上表最终848项。

首次工具治理受沙箱临时Git目录权限阻断；保留`governance.log`失败，不冒充业务失败或通过。授权范围内在可写环境重跑为`governance-retry.log`97项结果。其余日志为`frontend.log`、`readiness.log`、`verified-final.log`；不将Python／JS语法检查或模板渲染当作浏览器验收。

## 并发、迁移与独立终审

- 四店一次创建四笔订单，只占1组；任一店库存或后续写入失败时，无CheckoutRequest、订单、预留、清理任务或库存日志残留。按原快照返回商家名，不受后来改名影响。
- 最后一个组名额由两个独立连接竞争，只能一个成功。付款／商家关闭持有外层事务时，以递归pg_blocking_pids证明两个新结算均实际等待，再验证名额和paid库存守恒。
- 三组多店同时超时按3组计，部分支付后剩余超时仍计；首次拒绝后在无外层事务环境核验冷却已提交，刷新不延长。取消和超时分开计次、24小时升级和消费游标均通过。
- 新`orders.0008_checkout_risk`在真实MigrationExecutor的0007→0008路径验证：合成可信与异常历史只生成3条事件，原CheckoutRequest／OrderInfo／OrderGoods／StockHold／Inventory／InventoryLog／ReservationPolicy／SKU全部列摘要不变；重复回填两次仍为3条。未来、逆序、缺释放时间、商家取消及未受管记录不形成处罚。
- 独立只读终审发现的1项P2已按RED→修复→最终集成处理：只在本次reserved→released数量大于0时记录事件。复核无该项遗留；正常新建和异常历史两条路径均有覆盖。

## 启用、交付与未覆盖

**新0008尚未应用业务库，新后端规则尚未重启启用。** 本机继续运行此前20:58的已授权版本，见[既有启用记录](../2026-11-03-checkout-light/activation.md)。正式启动脚本先运行只读迁移预检，失败即退出，随后才可能停止旧服务；不会自动迁移，也没有运行第二份后端。

业务库须另行备份、授权应用0008、核对原业务摘要，再重启唯一后端／清理进程并验证接口。本轮没有业务库写入、真实账号下单、真实支付／退款、真实模型质量或浏览器人工验收；7项OCR／视觉专用数据库测试未重跑，不宣称生产容量或无死锁。

本轮没有创建新工作区，旧受保护工作区与其他任务产出保留。最终实现指纹为`76d18fd740c28161d9c0af3a43448aa62f3c719ee4e0e3af1dba6a507653b397`，逐文件清单见主目录`.scratch/checkout-groups-20261103/source-fingerprint.json`；源码与最终848项集成快照一致，只有core／orders／web版本递增，允许范围外既有增量摘要及真实index保持不变。本轮新增文本的旧品牌名扫描通过。

回收前按全ID、任务标签、内部网络、tmpfs和无业务挂载核对两个容器，确认随机测试库0残留后正常移除2个容器及1个网络；没有删除业务卷或复用的测试镜像。完整记录为同目录`closeout.json`。Git提交／推送／PR及生产发布均未执行。
