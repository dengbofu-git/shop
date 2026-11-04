# 本地启用：商家独立订单与结算组风控

时间：2026-11-03 22:21:56（Asia/Shanghai）完成重启，22:23后完成实际接口与进程复核。用户先要求重启后端，预检确认缺少0008后，明确授权“备份、迁移并重启”。本次没有Git提交／推送／PR、生产发布或其他数据库清理授权。

## 来源、备份与恢复

- 唯一运行源为主工作目录，分支`codex/core-pg-retirement`，基线HEAD `a864f909b57ab0a53d213472f6f317b09eb8ee4e`及本地已验收增量。实现指纹`76d18fd740c28161d9c0af3a43448aa62f3c719ee4e0e3af1dba6a507653b397`与[848项隔离验收](verification.md)一致。
- 先核对Web／MCP／到期清理进程树、知识Worker容器全ID、镜像和主目录只读挂载，再停止这些已归属的应用写入进程。PostgreSQL、Redis及其他项目服务保持运行。
- 冻结后在只读REPEATABLE READ事务导出快照，`pg_dump --snapshot`及原数据摘要使用同一快照；原生备份1,512,184字节，SHA256为`d4b8501af50d3e2e3a8cbb7003e5ea7a4c2ba538111bd2c5ad9fec1a2374459f`。
- 备份在相同PG16／pgvector0.8.7镜像的隔离tmpfs容器实际恢复，`pg_restore --exit-on-error --no-owner --no-acl`成功。**74张表、7,245行、66个序列状态及原约束、索引、列和扩展全部核验一致**。74表包含django_migrations，旧业务表为73张。备份仅为本项目数据库，不包含集群角色口令或媒体文件。
- 首次结构比较因正常PG往返表示差异拒绝放行，尚未执行业务迁移。独立复核后，仅忽略已删除列留下的物理attnum空洞，继续严格检查可见列顺序；仅对`ai_document_status_valid`的两种完整数组类型转换表达式确认等价，并在源库和恢复库各执行11组只读、NULL安全表达式探针。其他差异仍严格拒绝，全部原表行摘要和序列自始一致。

备份保存在主目录`.scratch/runtime-activation-20261103-groups/backups/pre-0008.dump`，校验收据为`.scratch/runtime-activation-20261103-groups/backup.json`；私有备份不入Git。恢复验证容器无主机端口、网络连接、业务挂载或持久卷，验收后已正常移除，保留原生备份。

## 迁移结果

再次校验数据库名与PG集群身份、代码指纹及迁移计划，确认唯一待执行项为正向`orders.0008_checkout_risk`。在同一数据库连接及外层事务锁定旧表，设5秒锁等待及90秒语句超时，再核对冻结点与备份摘要一致，执行迁移并在提交前复核。

| 检查 | 结果 |
| --- | --- |
| 新表 | ReservationRiskEvent、ReservationRiskState创建成功 |
| 原73张业务表全部行 | 数量及全列内容摘要不变 |
| 旧订单关联／截止／金额／状态、StockHold、库存、历史TTL策略 | 全部保持原值；没有重新分组或延长期限 |
| 旧序列、列、约束、索引及扩展 | 不变；迁移历史序列只随正常新增记录推进 |
| django_migrations | 保留全部原行，仅新增orders.0008一行 |
| 历史风险事件 | 精确匹配冻结时符合条件的历史释放集合，本库为0条 |
| 风险状态 | 0条，迁移不伪造冷却 |
| 待迁移 | 0 |

迁移事务已提交，没有回退业务数据库。前后摘要与新增事件核对在恢复后台进程之前完成，后续正常到期清理产生的业务变化与迁移保持区分。原始收据为`before.json`、`verified-before.json`、`migration.json`。

## 重启和实际验收

通过正式`tools/runtime/preview.ps1 -Python .scratch/runtime-py313/Scripts/python.exe -Restart`启用Web8000及MCP18082，预检确认零待迁移后启动；隐藏窗口启动同源30秒清理进程，并启动原知识Worker容器，镜像未变。生效版本core0.18.0／orders0.8.0／web0.38.0，carts0.4.1／users0.4.4等版本保持。

| 实际只读检查 | 结果 |
| --- | --- |
| login／buyer_orders／buyer_support页面 | HTTP200 |
| 本人买家实际GET结算预览 | checkout_sku_limit=20、reservation_ttl_seconds=900、max_unpaid_checkouts=3 |
| MCP健康 | ready，2 workers，0活动会话 |
| 数据库 | 仅PostgreSQL/default，0待迁移，无MySQL驱动 |
| 知识Worker | 代码逐文件指纹一致、PG集群和库身份一致、0待迁移，无MySQL驱动 |
| 运行唯一性 | 8000／18082各1个监听，8873为0；无其他后端来源，原进程均退出 |
| 到期清理 | 同源唯一进程树运行，已跨多个30秒周期，错误日志0字节 |

实际检查只生成内存认证凭据并执行读取，没有登录写入、创建测试订单、扣款、模型调用或改动真实采购车。真实支付／退款、生产部署和人工浏览器完整交易不在此次验收范围。

收据位于主目录`.scratch/runtime-activation-20261103-groups/`：`restart.json`、`after.json`、`unique-runtime.json`、`worker-audit.json`、`recovery-cleanup.json`。没有创建／删除工作区或提交推送，既有未提交成果继续保留。
