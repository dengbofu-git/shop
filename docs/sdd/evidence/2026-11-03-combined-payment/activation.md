# 本地启用：合并付款与商家独立订单

时间：2026-11-04 09:32:56（Asia/Shanghai）完成最终服务恢复，09:33—09:34完成实际接口、进程及知识Worker复核。用户明确授权“备份、迁移并重启启用”。本次只启用已审查的合并付款，不包含退款、真实商家分账、Git交付或生产发布。

## 来源与原生备份

- 唯一运行源为主工作目录，分支codex/core-pg-retirement，HEAD为a864f909b57ab0a53d213472f6f317b09eb8ee4e及本地验收增量；生效版本orders0.9.0／pays0.3.0／web0.39.0。实现指纹`cc1fcb2c3a54b546d37b5f6e3a4fd4e85fa4bccd80250f124cd004ab8f270d26`与[323项交易集成及146项前端验收](verification.md)一致，645个Python／JavaScript／模板／样式文件在主机和知识Worker逐项一致。
- 停止已核实归属的Web、MCP、到期清理和知识Worker，PostgreSQL及Redis保持运行。冻结后确认没有其他数据库客户端会话；在只读REPEATABLE READ事务内导出快照，原数据摘要与pg_dump使用同一快照。
- 原生备份：`.scratch/runtime-activation-20261104-combined/backups/pre-pays-0001.dump`，1,522,633字节，SHA256为`6d0f46afc8d7cbbf4a769da6b14828fc1b2b4c016fca466dfa6c64d80fe2a26b`。迁移前再次核对文件大小和摘要；私有备份不入Git。
- 以实际业务PG镜像digest创建无网络、无主机端口、无业务挂载的tmpfs恢复容器，pg_restore --exit-on-error实际恢复成功。**76张public表、7,304行、67个序列，以及可见列、约束、索引和扩展一致**。比较只规范化pg_dump正常往返的已删除列物理位置及此前明确审查的单个CHECK表达式表示，不忽略任意结构差异。

备份范围为本项目数据库，不含媒体文件或集群角色口令；摘要比较不宣称逐项核验了ACL、视图、函数或触发器的全部定义。

## 迁移及数据保持

再次核对数据库名与PG集群身份、完整源码、备份和唯一待执行计划为正向pays.0001_initial。对原表加锁并设置5秒锁等待、90秒语句超时，在同一连接与事务中应用、核验后提交。

| 检查 | 结果 |
| --- | --- |
| 新表 | PaymentOrder、PaymentAllocation、PaymentReceipt，仅新增3张表 |
| 原业务表 | 75张原表全部行数及全列摘要不变，包含订单、明细、库存、预留、风控与策略 |
| 原序列及结构 | 保持；仅django_migrations正常增加1行及推进自身序列 |
| 新序列 | 仅allocation、receipt两个ID序列 |
| 历史流水引用 | 0条，精确匹配本库非空payment_trade_no；只允许legacy_reference，不补造可信付款或received_at |
| 新付款单／分摊 | 启用验收时均0，没有创建测试业务付款 |
| 待迁移 | 0，历史迁移未改写 |

迁移已经提交，没有回退或用旧备份覆盖业务库。原业务表内容在最终HTTP验收前再次比对仍一致；后续正常业务和到期清理活动不等于迁移改变原数据。

## 服务恢复与实际验证

首次08:26:56完成启用，随后会话中断，复查发现本地应用进程已退出，日志含I/O operation on closed pipe。保留首次重启收据与中断记录；确认零待迁移后仅恢复同一版服务，**没有重复迁移**。最终Web／MCP与清理进程恢复于09:32:56。知识Worker容器仍为原完整ID、镜像和主目录只读挂载，当前启动时间09:24:56单独记录，不用旧收据冒充当前状态。

通过正式tools/runtime/preview.ps1启用Web8000及MCP18082。到期进程入口与Web一致加载应用、PostgreSQL和service.env，并在进入循环前核对数据库身份及零待迁移。

| 实际检查 | 结果 |
| --- | --- |
| 页面 | login、buyer_orders、payment、gopay、merchant_dashboard均HTTP200 |
| 新付款路由 | GET405、匿名401、商家403、非对象JSON400，证明新接口和服务端身份边界已加载 |
| 新前端资源 | 两个付款模板含combined-payment缓存版本，实际JS摘要与验收文件一致 |
| 可信通知入口 | GET302，只跳转、不确认付款 |
| 支付配置保护 | 收款方校验配置仍缺失，付款请求返回503／PAYMENT_NOT_CONFIGURED，不生成假链接 |
| MCP | ready，2 workers，0活动会话 |
| 运行来源 | 8000／18082各1个监听，8873为0；旧进程退出，只有主目录应用树和一份清理进程树 |
| 到期清理 | 跨多个30秒周期存活，错误日志0字节；两次只读观察见后台清理查询完成且state_change推进，没有由探针触发清理 |
| 知识Worker | Python3.13.18／Django5.2.18、仅default PostgreSQL，数据库身份一致，pays.0001已应用、零待迁移、无MySQL驱动；审计事务强制只读 |

接口验收只在内存生成短期身份，使用读取、拒绝请求及不存在的checkout编号探针；未保存认证凭据、创建订单／付款尝试、改动采购车、扣款、退款或调用模型。没有完整人工浏览器付款或真实支付宝联调验收。**代码与入口已启用，真实扣款仍需补齐并核验支付渠道配置**；独立售后仅保留子单归属，退款与商家分账另作任务。

## 收尾

恢复验证容器在中断后已不存在；按本次完整ID、精确名称及任务标签确认零残留，未重建或误删其他容器。备份文件大小和SHA再次通过，业务数据卷、原工作区及其他任务成果保持。本机原始记录在`.scratch/runtime-activation-20261104-combined/`：backup、verified-before、migration、restart-initial、interruption、restart、after、unique-runtime、expiry-observation、worker-audit及recovery-cleanup等JSON和脚本。Git提交、推送、PR和生产发布均未执行。
