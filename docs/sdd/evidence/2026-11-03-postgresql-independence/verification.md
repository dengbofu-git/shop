# PostgreSQL完全替换与旧源退役验收

日期：2026-11-03（Asia/Shanghai）。用户要求暂缓记忆管理，完整替换PostgreSQL后删除旧MySQL项目库数据、验证独立性，并授权暂停其他任务。该授权不包含本次Git提交、推送、PR、合入或生产发布。

## 源码与范围

- 基线：`a864f909b57ab0a53d213472f6f317b09eb8ee4e`；当前本地分支`codex/core-pg-retirement`，本次增量尚未提交。配置、工具、测试与文档对应[ADR0013](../../../adr/0013-postgresql-only-runtime.md)及[数据库规格](../../architecture/postgresql-unification.md)。
- core0.16.0、ai_storage0.8.1、support_ai0.32.5、goods0.7.6、orders0.6.2、supplier0.4.6、engagement0.2.5；web0.36.3为主目录原有独立增量，其五个文件与版本记录保留，未代提交。
- 正式配置仅支持PostgreSQL/default；拒绝legacy及未知模式。移除MySQL源导出、测试启动器和可选驱动安装文件；保留已有离线归档的准备／受保护导入／核验工具。评测及种子工具按PG数据库名、集群system_identifier双重核验后才访问数据。
- 专用OCR／视觉数据库夹具验证独立临时库身份，不再模拟MySQL后端；并发测试在真实PG执行。历史Migration与历史证据不改写；保留的MySQL文字为历史记录、迁移兼容分支或拒绝旧配置的负例，不提供正式MySQL运行入口。

## 独立验证环境与结果

使用独立内部Docker网络，仅有pgvector PG16和Redis7，无对外端口、业务数据卷或真实模型配置。测试镜像未安装MySQLdb/pymysql，3306不可连接。只读挂载同份源码后复制到Linux临时目录执行，避免Windows挂载的文件扫描延迟；未修改业务逻辑来绕过测试。

| 实际验证 | 命令／范围 | 结果 |
| --- | --- | --- |
| PG／Redis完整业务回归 | `python -B manage.py test orders inventory pays carts goods supplier engagement users support_ai ai_storage logistics --settings=tea_saas.pg_test_settings --noinput --verbosity 2` | 744项：737通过、7项专用数据库测试在该批跳过；36.633秒，退出0 |
| Paddle专用数据库 | 独立随机命名PG库，完整迁移后执行`ai_storage.test_paddle_document_database` | 4/4通过，6.312秒；在旧源清空后再次执行，随后删除本次临时库 |
| 视觉专用数据库 | 独立随机命名PG库，完整迁移后执行`ai_storage.test_vision_database` | 3/3通过，7.672秒；在旧源清空后再次执行，随后删除本次临时库 |
| 原生MCP | `python -B -m tools.tea_saas_mcp.agent_integration --unified-postgres --resident` | 19项通过；真实SDK→常驻HTTP→预热Django进程，外部模型调用0，临时库清理完成 |
| PG配置／入口／身份／转移契约 | `python -B -m unittest tools.tests.test_database_config tools.tests.test_pg_only_entrypoints tools.tests.test_postgresql_identity tools.tests.test_database_transfer -v` | 24项通过；旧入口先失败、退役后通过 |
| 前端回归 | `node --test client/tests/*.test.js` | 111项通过；覆盖保留的支付页增量，不表示该增量已提交 |
| 完整工具治理 | `python -B -m unittest discover -s tools/tests -v` | 94项：93通过、1项因Windows不允许创建测试符号链接跳过；46.508秒，退出0 |
| 模型及Git策略 | `makemigrations --check --dry-run --settings=support_ai.test_settings`；隔离临时index执行`python tools/git_policy.py verify`；`git diff --check` | 无模型变化；80个变更文件、15个模块归属、31个Python／JS语法检查通过；真实index及原有五文件与web模块记录保持 |
| 实际本机只读验收 | 登录页、买家订单页、推荐、当前身份、本人订单、咨询列表6个GET；常驻MCP本人订单及偏好读取 | 全部成功；单default/PG，待迁移0，MCP预热进程2个，真实模型调用0 |

主测试批与专用测试批合计覆盖上述744个业务用例，不能将主批7项跳过写为当批全通过。原始日志保留于主工作目录`.scratch/pg-independence/`：`business-pg-only.log`、`mcp-pg-only.log`、`canonical-tool-tests.log`、`frontend-tests.log`、`post-clear-*-database-tests.log`及`activation-audit.json`。完整治理检查、源码快照及回收收据也保存在该目录。

先前只读Windows挂载执行因测试需要临时写目录及文件扫描耗时而未完成；直接按文件启动MCP曾触发包导入失败。已改用Linux临时源码副本和Python模块启动并重新通过，失败日志保留，不计为验收通过。首次治理检查发现文档新增旧项目名，修正后完整94项重跑通过。实现文件指纹为`1c9bc5667f5d67c799771f2486646f984071f61e9d00c4d5c4e51e32e6a7275e`，逐文件清单在`source-fingerprint.json`；未把本地增量当成已提交SHA。可选OCR模型实机、真实支付渠道、真实模型回答质量与生产容量均不在本次范围。

## 旧MySQL项目库：先恢复核验，再清空

1. 核实原容器`master`、原数据卷及服务器UUID。原容器保持停止；维护辅助容器使用原镜像、独占来源卷、无网络及端口，删除前启用read_only和super_read_only。该实例另有其他项目库，未对其表执行清空或删除。
2. 旧项目库66张模型表共6,944行，与最终迁移归档逐表内容一致；另有`django_migrations`61行，共67表7,005行。没有需要补迁移的来源增量。
3. 最新原生备份`latest-source-mysql.sql`共1,588,313字节，SHA256为`bc380e0c5de58055b24413fe2e891b675843fdbd17541bdb25a73cd6a79bb487`。实际还原到另一无网络、无端口、tmpfs维护容器，66张模型表内容指纹和61条迁移记录全部一致。
4. 删除脚本必须显式`--apply`，先验证备份指纹、恢复收据、来源身份、67张InnoDB表集合及内容、无跨库外键／事件、来源卷唯一挂载。逐张执行限定项目库名的TRUNCATE，逐表记录前后行数；存在执行日志时禁止自动重试。
5. 已执行结果：**67张表、7,005行→0行**，表结构保留。恢复只读标志后独立复核；维护容器停止再启动，重读全部67表仍为0，read_only和super_read_only均为1。其他库名集合保持，未向其表写入。
6. 两个维护辅助容器随后停止并移除，不删除原卷；原`master`仍停止，备份仍保留。最后复核时间`2026-11-03T09:38:56Z`。这证明表内记录清空及重启后持久状态，不宣称磁盘安全擦除。

私有收据：`.scratch/pg-independence/mysql-retirement/receipt.json`、`clear-receipt.json`、`post-clear-receipt.json`。凭据、行级归档和原库名不写入本证据。独立审核无Critical／Important问题；一项Minor为单次维护脚本先落“cleared”日志再在finally恢复只读标志，已通过另外的进程重启、标志及全表零行复核消除本次状态歧义，未把日志标签单独作为完成依据。该一次性脚本不作为正式产品工具交付。

## 唯一本地运行及恢复边界

本机Web8000、MCP18082、知识Worker及30秒库存到期进程均使用主工作目录及统一PG。实际数据库73张模型表、7,183行，知识文档18、片段152；相对11月2日冻结归档只有浏览、预留限流及订单正常运行状态的变化，未把它们覆盖回历史值。

主Python运行环境已卸载mysqlclient，Worker镜像无MySQL驱动；活动私有配置已移除DB_*及AI_POSTGRES连接键。`AI_POSTGRES_VOLUME_NAME`仅为既有PG数据卷名兼容变量，保留原值并核对实际挂载，不提供第二数据库连接。

本次另存当前PG原生备份`current-postgresql.dump`，1,512,184字节，SHA256为`cb8173417c37a99bd7aad6461d3c50e0d70a0572e94ac91958408d703f73c81c`；本日没有再次实际恢复该PG备份，前一日PG恢复证据见[首次迁移](../2026-11-02-postgresql-unification/verification.md)。恢复旧MySQL备份只能在隔离维护环境进行，不能重新启用legacy模式或覆盖已接收新写入的PG。

本次仅本地实现与启用，没有新增Migration、Git提交／推送／PR或生产发布。既有旧工作区的独有未提交内容继续保留，未被声明为当前运行版本。本次PG／Redis隔离测试容器与网络、MySQL维护辅助容器均已回收。

临时分支`codex/core-pg-independence`的代码已核对保留于主工作目录，没有运行进程或容器挂载；托管归档工具返回“The task's primary checkout cannot be removed.”，因此临时工作区及其本地分支保留，状态为`blocked-primary-checkout`，未强删或绕过保护。待Codex解除主检出绑定后才能正常归档；这不影响PG独立运行及旧库清空结果，也不表示本地资源已全部回收。收尾收据在主目录`.scratch/pg-independence/closeout.json`。其他任务继续暂停，等待用户恢复；暂停不扩大其Git发布授权。
