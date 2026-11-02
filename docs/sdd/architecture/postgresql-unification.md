# PostgreSQL 单库迁移与事务边界

规格0.1.0，2026-11-02。来源为用户明确批准的独立统一数据库任务及[ADR0012](../../adr/0012-unified-postgresql.md)。记忆候选、独立业务任务和经历索引的新功能未实施。

## 当前代码契约

- 默认统一PostgreSQL，仅配置default。AI App读写、显式连接和事务通过ai_storage.database.alias()选择同一连接；schema和代码模块仍分别归属。
- POSTGRES_HOST/PORT/NAME/USER/PASSWORD为运行配置。legacy模式沿用DB_*与AI_POSTGRES_*，仅供来源工具、旧隔离夹具及明确恢复，不自动回退。
- 身份/对象权限、公开DTO、PII、幂等、会话revision及Redis订单位置规则保留。数据库同库不扩大MCP工具权限，不自动增加跨表用户访问权。
- 来源ID及业务字段保持；NULL币种仍未知，不推断或换算；库存预留、消耗和释放不变量保持。
- 账号明确大小写兼容，使用与Django PostgreSQL iexact一致的Upper唯一约束，商品导入显式去重；不把MySQL默认排序当成完整跨语言业务规格。

## 转移工具

`tools/database_transfer.py`仅用于离线转移，含export、prepare、import和verify。源配置必须显式legacy，源连接设只读/可重复读；目录必须不存在。归档覆盖所有模型表（含自动中间表），未知/缺表即拒绝，不拷贝旧django_migrations掩盖缺表。

目标必须是显式tea_saas_unified_*新库且没有应用表。prepare执行未经改写的迁移并登记随机token和种子内容基线。import校验所有归档文件和内容指纹、模型列契约、准备token/状态；在同一事务中先按表名排序取得全部目标表的ACCESS EXCLUSIVE锁，再核对种子基线、替换种子，避免核验后发生并发写入而被覆盖。锁超时即失败回滚，不接受任意非空数据库。全事务内导入、序列校准、外键验证和逐表内容核对，成功后标applied且拒绝再次导入。

规范化比较包括Decimal固定字段精度、UTC时间、UUID、JSON、向量、布尔及NULL；金额非有限值或需要舍入才能适配目标精度时直接拒绝。按行内容哈希排序，避免物理顺序或数据库排序差异误报。源MySQL无时区datetime按项目既有USE_TZ=True的UTC存储约定处理；归档包含私人业务数据，不入Git。

## 切换顺序

1. 真实PG完整回归、全部迁移及原并发用例；合成与真实来源导入演练，备份实恢复与73表内容核对。
2. 仅暂停本项目Web/MCP、库存到期进程及知识Worker写入，记录所有进程/挂载来源，不停止其他项目数据库。
3. 对冻结来源导出最终归档与原生备份，建立新的统一目标，逐表核验、校准序列、检查角色/订单归属/库存；不写源库。
4. 保存本地配置恢复副本，切换POSTGRES_*和unified模式；Web/MCP、知识Worker和到期进程统一启用，验证唯一运行来源。
5. 原MySQL及旧AI库保留，旧库不能继续接收本应用写入。新库已有新写入时不允许盲目切回旧库。

## 验收与未覆盖

必须证明AI和业务同事务回滚、原数据库ID/值一致、重复/篡改/非空目标拒绝，查询/向量守卫/全文ACL、订单并发/支付幂等/取消释放/发货及咨询评价正常。CI使用pgvector PG16和独立Redis；可选OCR实机/PDF依赖、真实支付/模型质量仍独立验收。

实现、演练、切换和发布分别记录。此次实际状态见[迁移证据](../evidence/2026-11-02-postgresql-unification/verification.md)，不能由源码默认配置推断本地业务库已经切换。
