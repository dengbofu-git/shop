# PostgreSQL 独立迁移验收

2026-11-02，Asia/Shanghai。用户要求先完成“统一 PostgreSQL”独立迁移。源码基线为 `eb39a3e9c41f6604e4f366a58796e36532d26030`，实施分支 `codex/core-postgresql-unification`，唯一运行代码目录为 `主工作目录`。实施验收与Git交付分别记录；用户随后授权“创建并推送MR”，最终源SHA、同步main及交付检查记录于PR正文，不自动合入。不包含三层记忆新功能，也不是生产发布。

## 已实现并本地启用

业务 MySQL 和原 AI PostgreSQL 的应用表已进入新库 `tea_saas_unified_20261102`。Django 仅注册 PostgreSQL/default，AI 路由和显式事务使用同一连接；没有用两个别名指向同库来冒充跨模块原子事务。Redis、媒体及 PDF 文件保持原存储和身份边界。

原业务库只读导出，未改表或回填；旧 MySQL、旧 AI 库和原生备份保留用于恢复。新目标通过全部现行 Django Migration 建表，历史脚本未修改，不复制旧 django_migrations 伪装建表。新增 users.0009 仅在新统一库实施 Upper(username) 唯一约束，兼容 PostgreSQL 下 Django iexact 登录身份语义。

Web、常驻 MCP、知识 Worker 和每30秒库存到期/采购车清理均已加载统一配置。Worker 镜像为 `sha256:ac2432833a9751c8e970cc89ee5e034852528f5943a6b1b57c82c35f16010026`，容器内验证不含 MySQL 驱动。MySQL 驱动只作为独立来源导出工具的可选依赖保留；旧运行环境尚有该驱动不代表应用仍连接旧库。

## 最终冻结与数据核验

冻结前 MCP active_sessions=0，知识导入无运行中租约。仅停止本项目 Web/MCP、到期清理及知识 Worker；原数据库服务未停止。最后快照于09:53 UTC（17:53本地）生成，区别于较早的7,068行演练快照。

| 核验 | 最终结果 |
| --- | --- |
| 完整来源覆盖 | 73张模型表（含自动中间表），7,183行；不含旧迁移记账表 |
| 字段与内容 | 原ID、金额、时间、JSON、向量、NULL等规范化逐表哈希一致 |
| 自增序列 | 65个序列均在现有最大ID之后，校验不消耗序列 |
| 历史币种 | 138笔订单及137条明细仍为NULL，不推断、不换算 |
| 来源冻结核对 | 导入后再次只读读取两份来源，仍与最终归档一致 |
| 非空目标准备/重复导入 | 两者均拒绝，拒绝后目标内容仍一致 |
| 备份恢复 | 最终统一库原生dump恢复至另一隔离空库，73表全部内容一致 |
| 启用后只读复核 | 7,183行与冻结归档一致，待执行Migration为0 |

归档manifest SHA256：`7f77f966a3c789e61bc5654f36a2176af6d919d8cac305c99146b24f19d38257`。

| 最终原生备份 | 大小/字节 | SHA256 |
| --- | ---: | --- |
| MySQL来源 | 1,588,099 | `a495153433572ff7e91f6f334f9539f9bae60d321ecfe90a9a4d6577b5af4a19` |
| AI PostgreSQL来源 | 1,091,263 | `30a96e54480bf4c7a8e20d5a4b45bc2ee84a96f294ffbb95bc22315b3cf8aa9a` |
| 统一PostgreSQL | 1,512,141 | `14a345f73a942bbd6f3cbc99f3811caf6790c178d0081dd7eb59672dbc311a4b` |

私人归档、两次演练及最终备份、本地配置恢复副本存放在本机 `.scratch/pg-unification/`，均不入Git。本次恢复证明来自统一PG备份实际还原并包含全部来源内容；不宣称此次另将MySQL dump还原至MySQL。

## 验证命令与实际结果

测试库是独立pgvector PostgreSQL16容器和独立Redis容器，与业务库无挂载共享。`TEA_SAAS_PG_TEST_PORT`、`TEA_SAAS_PG_TEST_PASSWORD`及`CART_TEST_REDIS_URL`只指向这些临时资源；未向业务库运行测试。

```powershell
python manage.py test orders inventory pays carts goods supplier engagement users support_ai ai_storage logistics --settings=tea_saas.pg_test_settings --noinput --verbosity 2
python -m unittest discover -s tools/tests
```

- 最终业务PG＋Redis：735项，724通过，11跳过，0失败；包括真实并发下单/取消支付、发货、商品导入、咨询评价、采购车幂等和Redis当前页订单映射。对应完整日志为本机 `full-pg-redis-final.log`。
- 11项跳过明确属于独立PDF/OCR数据库夹具或PDF Worker可选依赖条件；不能把这些算作已通过。一次未注入Redis配置的前序运行有48项跳过，已由最终启用Redis的运行取代。
- 工具治理：80项，79通过、1跳过，0失败；覆盖配置、归档篡改/缺失拒绝、数据规范化及既有Git工具契约。
- 原生常驻MCP隔离验收：19项通过，实际SDK→常驻HTTP→预热Django进程，业务与AI共用一个临时PG；模型调用0，资源清理成功。
- 前端回归109项通过。独立PG页面验收14项通过：双店拆单、取消精确释放、合成支付/发货/收货/评价、详情评分、商品咨询双向消息、跨账号隔离、历史菜单键盘与390px视口、断网重试。没有真实支付交易。
- 新库只读实机：登录页、订单页、推荐接口、会话身份、本人订单及咨询列表均200；真实常驻MCP读取本人最近3笔订单和偏好通过，模型调用0；知识库18个文档、152个片段可读。
- 实际知识Worker内独立检查：仅default、AI alias=default、PG连接成功、目标库正确、MySQL驱动不存在。
- 模型/Migration漂移检查为No changes detected；独立临时索引静态校验89个变更文件、15个模块、59项Python/JS语法通过，真实暂存区不变。该检查不等同推送前同步main或远端CI。
- 实际Python3.13环境以`uv pip check --python`离线核对92个包，全部兼容；该环境未安装pip模块。最初默认UV缓存写入被Windows沙箱拒绝，改用本任务目录缓存后检查成功，未因此安装或下载任何包。

未提交实现文件的SHA256集合指纹为 `5c11e54a48f172d5c9a5bde581d7a529853393c1ff77ab57ba697bc954c3a720`，包含源码、测试、配置模板、依赖与版本清单，不含本文和私人归档。逐文件摘要保存在本机source-fingerprint.json，弥补仅记录旧HEAD不能复现未提交增量的问题。

10:07 UTC最终运行盘点：Web8000唯一监听PID29156，MCP18082唯一监听PID33716、预热Worker2个，到期清理launcher12224。四类服务均属于同一本机持久主工作目录，清理日志无错误。临时PG/Redis容器和8879合成页面服务已回收；原库、备份和其他任务Worktree保留。

## 独立审查与修复

执行一次新上下文全分支审查，3项Important，均先复现失败再修复；8项定向用例通过，之后上述735项全回归通过。

1. 目标基线检查与TRUNCATE存在并发窗口：先按固定顺序获取全部目标表ACCESS EXCLUSIVE锁，再比对基线，5秒锁超时回滚。真实第二连接写入被55P03拒绝，不能被悄悄覆盖。
2. Decimal规范化可能静默舍入：非有限值或超出目标字段精度即拒绝；1.234迁入两位小数字段的反例已覆盖。
3. Lower唯一约束与PG iexact的Upper比较不一致：新约束统一采用Upper，希腊σ/ς登录身份碰撞由数据库阻断。未改已交付的历史迁移。

## 实施裁定和限制

- 复用干净的主代码目录创建开发分支，未另建Worktree；受保护的旧Worktree属于其他既有现场，未删除或启用。
- 账号和导入重名显式兼容大小写；不声称PG默认排序等价于MySQL utf8mb4_unicode_ci的全部语言规则。字段边界保持，原先超长的测试夹具已修正，没有扩大真实业务字段。
- Redis继续承担临时缓存、限流及24小时当前页订单位置映射；文件不迁入数据库。迁移没有扩大MCP或租户权限。
- 新库恢复业务写入后，不能只改配置切回旧库，否则会丢失切换后的新记录；需要另行冻结、核对并迁移增量。保留旧库不是双写。
- 未做生产发布、真实支付/退款、真实模型回答质量或实体手机全面验收。本地角色沿用现有PG运行账户；生产最小权限、备份异地化和恢复演练周期另行设计。

规格见[统一数据库契约](../../architecture/postgresql-unification.md)，决策见[ADR0012](../../../adr/0012-unified-postgresql.md)。模块版本以versions/modules.json为准。

Git交付补充：首次远端命名检查发现本文物理路径包含退役工程名；已统一改用主工作目录表述，未放宽命名门禁或修改实现。随后执行项目命名及模块归属6项回归通过。
