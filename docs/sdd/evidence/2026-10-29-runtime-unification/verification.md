# 运行基线统一与数据库迁移验收

2026-10-29。用户明确要求只保留已升级的运行版本，完善功能并执行数据库迁移。分支 `codex/support-ai-mcp`，基线 `c5b09f7d5ac3c5bd124028a8d4a870f438fce389` 的未提交增量。本轮运行整合为core0.11.0、support_ai0.28.0、goods0.7.2、ai_storage0.7.2、engagement0.2.3；流式前端测试时web为0.33.0。验收之后同工作区出现另一个任务的购物车／币种改动及web0.33.5，本轮保留该并发工作、不覆盖其版本，也不将先前103项前端结果冒充随后购物车增量的验收。

## 原因与纠正

当前客服分支未整合已交付的Python升级，临时重启时错误使用Python3.9，而原业务运行环境已经是Python3.13。新版环境没有PyMySQL/pytz是升级后移除旧依赖的正常结果，正确处理是整合mysqlclient与ZoneInfo升级，不是回退解释器或重新加入旧依赖。

本轮审阅并应用既有升级提交 `7202aab9b4a4ddf2a702067b5beb459b52cb195c` 的运行配置、依赖及兼容调整，保留现有MCP追踪、常驻服务和流式改动。没有切换已有分支、自动stash、重写历史或覆盖原工作区其他未提交功能。修改和测试范围以本记录各阶段为准，不能单凭当前脏工作区的一个HEAD复现全部现场。

## 唯一部署基线

- Web与Django数据Worker：Python3.13.18 / Django5.2.18；MySQL使用mysqlclient，订单日期使用ZoneInfo。
- MCP SDK：独立依赖环境，但同为Python3.13.18，锁定MCP1.29.1。运行配置只指向当前工作区 `tools/tea_saas_mcp/.venv`，不再使用旧3.12 SDK。
- 正式本机入口为 `tools/runtime/preview.ps1` → `tools/runtime/backend.py` → `run_support_backend`，先预热MCP再启动Web。入口及管理命令均拒绝旧运行时，管理的MCP服务也要求Python3.13。完成一次启动及一次 `-Restart` 实际验证。
- 已删除此次临时 `.scratch/runtime/backend.py` 和 `runtime_settings.py`；不删除其他工作区代码或历史验收记录。
- 8000 Web、18082 MCP及知识Worker使用当前工作区代码。知识Worker原来已是Python3.13.18/Django5.2.18，本轮将其 `/app` 挂载统一到当前源；保留已有镜像，不更新推理模型服务。
- 原数据库配置通过指定env文件读取；媒体目录、PDF存储目录及Worker输入目录保持原路径。知识Worker配置通过只读 `/run/secrets` 挂载，凭据不写入代码或本记录。预览和遥测展示版本从 `versions/modules.json` 同一事实源读取。

## 实际验证

| 命令／检查 | 结果及范围 |
| --- | --- |
| 新版解释器 `manage.py test --settings=support_ai.test_settings --noinput -v 1` | 658项，620通过、38按可选条件跳过，41.838秒。隔离SQLite和合成模型；没有把这些跳过项声称为通过 |
| 新版解释器 `manage.py test goods.test_product_import support_ai.test_streaming --settings=goods.test_mysql_settings --noinput -v 1` | 41项通过，24.110秒；真实隔离MySQL库验证历史迁移到0012及商品导入、SSE保存和重放，测试库清理完成 |
| 新SDK `python -m unittest tools.tea_saas_mcp.test_resident tools.tea_saas_mcp.test_server -v` | 19项，18通过、1可选条件跳过；常驻池、权限、故障监督、协议和隔离。该跳过用例未设置TEA_SAAS_TEST_PYTHON，真实集成另行覆盖 |
| 新版解释器 `python -m tools.tea_saas_mcp.agent_integration --mysql --postgres --resident --profile-output .scratch/runtime/py313-mcp-profile.json` | 19检查通过，一次性MySQL容器＋随机PostgreSQL测试库＋真实SDK与预热Worker；授权、两买家隔离、工具、HTTP/Preview、幂等与回收；真实模型调用0，资源清理完成 |
| 最终客服与HTTP日志回归 | 318项通过，20.977秒；覆盖新增版本读取和管理启动门槛后的行为 |
| `manage.py test tea_saas.test_runtime_entry --settings=support_ai.test_settings` | 2项通过；旧解释器在读取环境文件前被拒绝，直接管理命令不能绕过门槛 |
| `node --test` 当前client/tests与流式协议测试 | 103项通过 |
| 新Django渲染模板＋Edge浏览器流式验收 | 5次合成请求通过；进度和核验文本先到、保存后展示来源、断线保留请求ID、503清除临时文本、换账号停止旧请求；无浏览器脚本异常 |
| `makemigrations --check --dry-run --settings=support_ai.test_settings` | No changes detected；历史Migration未修改，没有新增空迁移 |
| 当前实际服务 | 页面及流式JS为HTTP200，未登录问答为401；MCP ready、2 workers/2 available、0 active sessions。知识Worker容器探测Python3.13.18、Django5.2.18、support_ai0.28.0、两库SELECT1通过 |

本机输出在忽略目录 `.scratch/runtime/`：`py313-full-tests.log`、`mysql-migration-tests.log`、`py313-mcp-integration.log`、`py313-final-support.log`、`frontend-tests.log`、`restart-verification.json`。不保存真实问答、密码或模型请求正文。

## 数据库实际变更

迁移前只读盘点：MySQL只有 `goods.0012_productimportjob` 需要实际建表；PostgreSQL的ai_storage结构迁移已经齐全。在隔离MySQL验证通过后，停止已确认身份的旧服务树，记录MySQL原表DDL与行数快照，严格断言唯一待执行结构迁移，再应用该迁移。

- MySQL新建 `goods_product_import_job`，新表初始为空，原表结构及业务表行数不变。
- 随后用标准migrate补齐路由跳过的账本：default记录4条ai_storage迁移，ai_storage记录55条其他App迁移；路由仍阻止这些App在错误的库执行结构操作，没有跨库创建业务表。
- Django post_migrate同时补齐权限／内容类型元数据。相对迁移前，default的auth_permission增加32行、django_content_type增加8行、django_migrations增加5行；这不是订单、商品或用户数据新增。首次账本检查因把权限元数据也要求行数不变而中止；核对属于正常post_migrate后，将元数据与业务表分别验证并完成后续账本，没有自动回退已执行的迁移。
- 最终两个数据库迁移计划均为空，标准migrate检查通过；两库补账本期间业务表行数保持不变。PostgreSQL无新增结构迁移。

结构／行数快照和结果位于 `.scratch/runtime/migration-schema-before.json`、`migration-result.json`；快照不包含业务行内容，不将其描述为完整数据备份。没有修改、删除或重命名历史Migration。

## 边界

本次已实际迁移数据库、切换本机服务及知识Worker挂载。未提交、推送、创建／合入PR或发布标签；没有删除其他任务工作区。未重新评估真实DeepSeek回答质量、GPU OCR准确率或第三方推理服务版本；可选条件跳过不作为验收通过。
