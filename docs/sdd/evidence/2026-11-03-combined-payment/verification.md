# 买家合并付款验收

启用补记：2026-11-04已获单独授权，原生备份实恢复核验后应用pays.0001并统一重启；中断后同版恢复及最终只读验收见[本地启用](activation.md)。下文“未启用”等表述保留实现交付时点。真实支付配置仍缺收款方校验，未进行真实扣款。

任务始于2026-11-03，最终核验于2026-11-04（Asia/Shanghai）。源分支codex/core-pg-retirement，HEAD为a864f909b57ab0a53d213472f6f317b09eb8ee4e且保留既有大量未提交增量。本次没有提交、推送、PR或生产发布；本文绑定工作区源码，不以旧HEAD冒充新实现提交。

## 已批准范围及实现

用户要求买家合并付款，商家独立订单、履约与售后；进一步确认本次只实现付款，售后保留子单边界，退款另做。新增付款单、不可变商家金额分摊、统一支付宝流水收据及新pays.0001_initial；订单创建结果与旧付款入口接入合并服务。页面保留提交前“提交订单”，保存后显示商家金额和一个“合并付款”按钮。

订单头是含运费的最终应付：商品金额加运费必须等于头金额，父单只求和各头金额。首次准备可排除已关闭／已付子单；一旦签发，成员、金额及最早截止固定。变化后不自动重开其他金额，旧链接迟到到账保留待核验，不复活库存。新旧入口共享交易号唯一性；正常到账整组原子确认，重复实际到账单独保留，不覆盖原付款。退款、真实渠道关单与商家分账未实现。

规则见[合并付款规格](../../modules/trade/combined-payment.md)及[ADR0016](../../../adr/0016-combined-checkout-payment.md)。版本orders0.9.0／pays0.3.0／web0.39.0；保留外部前端0.38.2的简洁提交文案、已启用的结算组风控和商家销售范围说明。

## 环境与实际命令

使用本任务专用Docker内部网络及tmpfs PostgreSQL16、Redis，无主机暴露端口、业务库挂载或业务数据；源码只读归档，不装载真实.env或密钥。每批使用独立随机测试库；所有支付／模型端点为本地不可用地址或测试替身。未调用真实支付宝或外部模型。

本机入口为Python3.13，隔离镜像为已有tea-saas-pg-independence-test:20261103；脚本及原始日志留在本机`.scratch/combined-payment-20261103/`，不随Git交付。以下命令均在项目根执行。

| 命令／范围 | 本次结果 |
| --- | --- |
| `python .scratch/combined-payment-20261103/run_tests.py payment-red-valid pays.test_combined` | RED：24个缺能力断言失败，随后实现；最初ModuleNotFound错误单独保留，不冒充业务断言 |
| `python .scratch/combined-payment-20261103/run_tests.py payment-green pays.test_combined pays.test_combined_migrations` | 首轮25项通过，exit0 |
| `python .scratch/combined-payment-20261103/run_tests.py legacy-duplicate-red pays.test_combined.CombinedPaymentTests.test_legacy_paid_order_keeps_second_real_receipt_without_mutating_payment` | 复现旧单第二笔真实到账触发PAYMENT_CONFLICT、收据事务回滚；修复后同标签GREEN通过 |
| `python .scratch/combined-payment-20261103/run_tests.py concurrency-fixed-green pays.test_combined_concurrency` | 7项通过，其中6项真实独立PG连接竞争，pg_blocking_pids确认锁等待；另1项合并后旧链接重复到账 |
| `python .scratch/combined-payment-20261103/run_tests.py commerce-final-complete orders pays inventory supplier admin_panel carts engagement` | 最终323项全部通过，25.599秒，exit0；包含34项本次支付／迁移／并发用例，测试库正常销毁 |
| `node --test client/tests/*.test.js` | 146项全部通过，无跳过，exit0；覆盖合并入口、权威总额、安全URL、旧响应、账号切换、失败重试及原前端行为 |
| `python .scratch/combined-payment-20261103/run_checks.py schema-checks check` | Django system check、makemigrations --check --dry-run通过，无模型漂移；payment、gopay、orderConfirm、buyer_orders四模板渲染通过；仅PG，无MySQL驱动 |
| `python tools/runtime/backend.py --check`（本地业务配置） | 只读预检按设计exit1：仅新pays.0001_initial待应用，拒绝未迁移启用；包装核验脚本确认此预期，未执行migrate或重启 |

首轮并发辅助方法误用了unittest内部属性名_outcome，7项中6项未进入竞争，不能视作业务失败；已改名并让线程提前错误原样传播，随后7项实际执行通过。最终集成前一批322项有1条旧断言仍预期第二笔到账被拒绝，按保留真实到账的新契约更新断言，生产修复未放宽验签或金额校验；上表最终批次全部通过。原始失败日志保留，不覆盖为成功。

## 关键证据与审查

- 正常三店／多店域逻辑、不同运费、固定截止及幂等复用；金额、商家快照、订单类型、币种、预留完整性不可信时拒绝。两个商家独立发货，另一店状态和库存保持。
- 通知校验签名、应用、收款方、状态及金额；GET不付款。跨目标同流水拒绝，同目标改金额拒绝；不同实际流水保存review收据。旧单已付款后第二笔到账保留完整收据，原订单所有列、库存与预留字典保持，重复该通知只有一条收据。
- PostgreSQL真实连接确认：同通知竞争仅确认一次；不同买家新／旧付款抢同流水，两个获胜方向均只有一个合法目标；付款先赢不释放paid库存；取消或到期先赢后到账进入review，无库存复活／重复释放，核验释放不额外处罚买家。
- 新0001真实降到尚无pays表再升级：CNY、未知币种、外币和未确认旧流水只登记legacy_reference；旧订单全列前后相等，不生成付款单、分摊或伪造received_at。正常测试库从零应用全部迁移也通过；未改历史Migration。
- 两轮独立只读审查核对金额、全局流水、锁序、全部子单原子性、失效和前端安全恢复。发现的旧单重复到账收据遗漏已先RED再修复并GREEN；最终未发现新增阻塞问题。代码审查不代替真实渠道或数据库运行证据。

## 源码及资源收尾

最终实现指纹SHA256：`cc1fcb2c3a54b546d37b5f6e3a4fd4e85fa4bccd80250f124cd004ab8f270d26`，绑定最终集成采样的Python、JavaScript、模板与配置；文件摘要保存在本机source-fingerprint.json。版本清单只在本次基线递增orders、pays、web三项；既有orders.0008等迁移保持，新迁移只增pays.0001。

使用独立影子索引运行`python tools/git_policy.py verify`，exit0：163个当前工作区变更路径、15个模块、82项Python／JS语法检查通过。这是全工作区静态盘点，包含此前WIP，不等于本次新增163文件，也不替代上表业务验证。真实Git索引摘要保持，未实际暂存、提交或推送；未获授权范围外既有文件与任务开始摘要一致，共享文件人工核对保留原增量。全部三份已有Worktree和分支原样保留，本次未建临时Worktree。

本次两个测试容器在完整ID／任务标签／纯tmpfs及内部网络核对后正常停止移除，任务网络已移除，剩余任务容器为0；缓存镜像和测试日志保留。初次清理时PostgreSQL因--rm在停止后自动移除，多余rm提示不存在；重新核对后完成剩余回收，未强制删除业务资源。未触及其他任务或真实数据库容器。

现有Web8000及MCP18082监听唯一且PID保持；清理进程继续由原主目录启动，未启动8873或另一版本。只读预检确认新pays迁移待应用，不能宣称本次已经启用。

## 未执行及启用条件

没有修改本地业务订单／库存、应用pays.0001、重启Web／MCP／清理进程／知识Worker，也没有调用真实支付或退款。现有唯一运行后端保持此前版本；本次新增付款能力尚未启用。开发目录的静态文件可以已被旧后端读取，旧创建响应缺少合并标记时前端只引导查看订单，不伪造新接口可用。

启用需另获授权：先对当前PostgreSQL原生备份并在独立目标实际恢复验证，再仅应用已审查的pays.0001_initial，核对原业务表内容、旧流水引用与新表约束，按唯一来源重启并核验接口、迁移计划和进程。收款方等支付配置仍需单独核对；本地流程可用不代表真实商家收款或退款可用。Git交付另行授权。
