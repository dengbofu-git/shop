# INV-CHECKOUT-LIGHT-20261103：轻量库存预留与结算范围

后续启用：2026-11-03 20:58（Asia/Shanghai），用户单独授权重启后端，本地唯一Web／MCP／到期进程／知识Worker已加载本轮代码；实际20种／900秒元数据及旧配置／截止指纹核验见[启用记录](activation.md)。下文“未重启”保留此前隔离交付时点含义，未新增Git交付或生产发布。

日期：2026-11-03（Asia/Shanghai）。用户经概念说明chat人工授权交接，要求完整实施已确认方案；来源摘要不冒充逐字原始对话。本轮仅本地源码和隔离验证，没有业务库策略写入、数据库迁移、服务重启、Git提交／推送／PR／合入或生产发布授权。

基线HEAD：`a864f909b57ab0a53d213472f6f317b09eb8ee4e`；开发分支`codex/core-pg-retirement`，含此前未提交PG-only、登录Hash和独立支付反馈增量。当前版本core0.17.0／orders0.7.0／carts0.4.1／web0.37.0，users0.4.4等原版本保持。对应[实施计划](../../../superpowers/plans/2026-11-03-checkout-light-reservation.md)、[规格0.4.0](../../modules/trade/stock-reservations.md)及[ADR0014](../../../adr/0014-light-checkout-reservations.md)。

## 实际变化

- `RESERVATION_MAX_SKUS_PER_CHECKOUT`服务端正整数配置默认20。预览／POST采购车按Redis实际已选集合计算，缺省/null/空列表不绕过；非空列表只选实际已选子集，重复SKU继续拒绝，客户端count／price不能替代服务端事实。直接购买算1种，单SKU多件仍按库存及原额度检查。
- `create_orders`是最终守卫，归一化后在到期扫描及SKU／库存锁之前拒绝超限；超限HTTP400/CHECKOUT_SKU_LIMIT及动态配置文案一致，不生成订单、预留或清理任务。
- 超限请求先只读解析，Lua快照在任何HSET升级前再次复核选择上限，覆盖预检查后并发勾选。拒绝路径不先消费旧清理任务；原编号重放、提交后清理及后台PG任务重试保留。新请求若旧消费区间未同步，安全返回CART_CHANGED，不重复购买。
- 新普通在线订单从不可变平台有效策略取得900秒，覆盖已有600／300及无配置店铺；保留旧策略TTL和其他三项额度，旧订单截止及重放不变。商家GET显示有效值／历史值／来源，PUT仅接受900确认且只更新三项额度、真实actor及依据审计，新建配置行显式900。没有批量回填或新增Migration。
- 原1800秒逐商家订单预算不扩大：两店各900可恰好通过，三店2700整次拒绝，有历史占用时更早受限。3笔／300件／60000元、占比／频控／冷却等原规则保持。
- 总数量先于SKU锁检查，其他非库存额度先于账本锁检查；最终库存及实物占比在锁内校验。仓库关联锁保留以保护is_active，不宣称不同SKU共仓不等待、FIFO或无死锁；冲突事务回滚，HTTP以CHECKOUT_BUSY要求原编号重试。
- 上限内仍一次PG外层事务，按商家创建订单、请求幂等、预留及采购车清理任务全部成功或回滚。锁在提交／回滚时释放，待付15分钟只保留预留记录。库存字段和物理仓库语义不精简，不增加额外Redis缓存、队列或库存分桶。

## 环境与真实命令

本轮使用独立内部Docker网络，PG16／pgvector0.8.7和Redis7.4.5-alpine均为tmpfs数据目录，没有业务挂载、持久卷或主机端口。运行镜像为此前已核验无MySQL驱动的测试镜像。每次从当前跟踪／非忽略源码打包到Linux临时目录，排除私有.env、Git和.scratch；仅使用合成密钥、账号与模型不可用地址。每次独立随机PG测试库，真实多连接锁测试不使用SQLite替代。

主目录执行器：`.scratch/runtime-py313/Scripts/python.exe -X utf8 -B .scratch/inv-checkout-light-20261103/run_tests.py <run> <test labels...>`。它串行管理夹具、执行`manage.py test ... --settings=tea_saas.pg_test_settings --noinput --verbosity 2`，数据库只指向本轮PG容器。

| 阶段 | 实际命令／范围 | 结果 |
| --- | --- | --- |
| 策略RED | `policy-red orders.test_checkout_policy orders.test_reservation_contracts` | 旧600／300／缺省期限、三店预算和API来源等不符合；18项测试包含18个失败断言／子例，日志保留 |
| 上限RED | `limits-red orders.test_checkout_limits` | 13项：11失败、1错误、1通过，确认原21种可创建、规范化重复未拒绝、预览缺配置、额度检查已取账本锁等缺口 |
| 首次定向GREEN | `core-green orders.test_checkout_limits orders.test_checkout_policy orders.test_reservation_contracts orders.test_checkout_light_concurrency` | 38项全部通过，2.393秒；随后增加并发勾选超限用例进入最终集成 |
| 阶段集成PG／Redis | `integration orders inventory pays carts goods supplier engagement users support_ai ai_storage logistics tea_saas.test_runtime_logging` | **811项：804通过、7项专用OCR／视觉数据库用例跳过**，34.159秒，退出0；本轮新增32项全部通过 |
| 前端 | PowerShell枚举`client/tests/*.test.js`完整路径后执行`node --test @testFiles` | **120/120通过，0跳过**；正式保存日志528.581ms；代理先验证新增行为缺失后再实施 |
| 模型状态 | `manage.py makemigrations --check --dry-run --settings=support_ai.test_settings` | No changes detected，无新增或改写历史迁移 |
| 工具治理 | `python -B -m unittest discover -s tools/tests -v` | 94项：93通过、1项Windows符号链接权限跳过；44.080秒 |
| 模板 | 隔离SQLite设置下调用模板loader只渲染四个变更页面，不访问关系数据 | orderConfirm／payment／gopay／merchant_inventory全部渲染通过；非浏览器验收 |
| Git策略与来源 | 隔离临时index执行`python tools/git_policy.py verify`、`git diff --check` | 110个当前变更文件、15个模块归属、51个Python／JS语法检查通过；真实index不变，历史Migration无改动 |

原始日志在主目录`.scratch/inv-checkout-light-20261103/`：`policy-red.log`、`limits-red.log`、`core-green.log`、`integration.log`、`frontend.log`；每批`*-source.json`记录实际打包源码指纹。运行过的失败保留，不算通过。

前端实际PowerShell命令：

```powershell
$testFiles=Get-ChildItem client/tests -Filter '*.test.js' | ForEach-Object { $_.FullName }
node --test @testFiles
```

治理／模板／策略日志分别为`governance.log`、`templates.log`、`policy.log`。最终实现指纹`cc6b20489b2b0ad837cf4c74c95252e7806bb9b4c899c60d15c02550aaf1b3cf`及逐文件清单在`source-fingerprint.json`；最终Python／JS／模板实现逐一与811项集成时的源码快照匹配。版本元数据和本轮文档随后同步，未把未提交增量冒充最终提交SHA。

## 覆盖的关键结果

- 20种且总件数200仍可创建；21种在expiry／stock锁前拒绝。配置2时3种同样拒绝。未选项不计、显式子集不多算、重复ID及服务层规范化重复均拒绝。
- 超限既不执行历史pending清理任务，也不升级旧Hash字段；预检查后并发多勾选一项，Lua拒绝且仅保留那次并发选择变化。
- ABC持有B直到提交，BD通过pg_blocking_pids确认真实阻塞；ABC提交后BD因B不足失败，D没有订单、预留、清理任务或库存／日志残留。富裕库存三买家累计51正确。
- 原事务提交后保持连接存活，另一连接NOWAIT仍能取得库存锁，订单仍待付款；证明锁随事务结束释放。
- 899／900秒边界、精确释放一次、已付不释放、付款／到期竞争及迟到付款异常处理通过；幂等同意图回放、异意图拒绝且期限不续。
- 仓库停用通过真实等待证明在已取得仓库关联锁后须等结算提交，不把保留关联锁误记为收窄优化。
- 原采购车故障重试、SQL确认窗口、原请求清理重放、提交期间新增加购、原支付及取消竞争、登录Hash计数均在本次PG集成通过。
- 前端默认20和非默认2按SKU行数防御，不按件数；超限回采购车且不继续POST，原待付款恢复入口保留；已有订单付款不限制行数，固定900 UI在旧后端上安全禁用保存。

独立终审（只读源码及日志）无Critical／Important／Minor遗留。其结论不冒充另一次测试执行。

## 启用与未覆盖

当前本机服务没有为本轮重启，不能声称实际运行中的新订单已900秒；此前PG-only启用状态与本轮源码状态分别报告。启用时须核对唯一源、配置、源SHA和真实操作者并单独授权；没有需要先回填旧TTL才能生效的隐藏步骤。

7项OCR／视觉专用数据库测试本轮未单独再跑；MCP专项、真实支付／退款、真实模型质量、生产性能容量和人工浏览器验收也未执行。本轮未改变这些服务的协议，不以Node假DOM或语法检查替代实机与生产验收。仓库关联锁的等待／潜在死锁及旧配置字段清理仍为已记录边界。

其他旧工作区及本次之前的未提交成果保留，未创建新工作区。测试前后核对允许范围外旧增量指纹、仅四个模块版本变化及登录修复；外部unpaid-recovery行为与旧测试保留通过。本轮PG／Redis容器、内部网络均已正常移除，随机测试库无残留；未删业务卷。完整收尾在`.scratch/inv-checkout-light-20261103/closeout.json`，不向来源chat跨会话回信。
