# 运行日志与 HTTP 关联验证

日期：2026-10-19，Asia/Shanghai。分支 `codex/core-runtime-logging`，从已有脏现场创建，保留命名、登录视觉、Redis、Agent 语义规划及其他既有改动。未暂存、提交、推送、创建 PR、部署或执行数据库迁移。

本轮范围为用户审阅方案的前两阶段；新增运行日志与请求关联，不实现业务审计、集中检索、定时清理或告警。有效规格见[SDD](../../modules/platform/runtime-logging.md)，配置见[运行指南](../../../运行日志.md)。

## 模块与实现

| 模块 | 当前版本 | 本轮增量 |
| --- | --- | --- |
| core | 0.4.0 | 安全格式化器、输出故障降级、可选单进程轮转、HTTP 请求日志及测试 |
| users | 0.2.5 | 注册、登录与短信模拟移除敏感控制台输出 |
| orders | 0.1.6 | 移除订单日志中的账号、单号与请求正文 |
| support_ai | 0.12.2 | 固定事件、异常类型与当前执行的 Trace 关联 |

版本从本轮开始时的工作区版本递增，没有覆盖已有版本增量。实现文件摘要见[清单](implementation-manifest.json)；previous_working_sha256 对应本轮写入前的实际工作文件，不等同 HEAD。未将其他未提交工作视为本轮产出。

## 自动化检查

业务 Python 使用本机现有 Conda 解释器。日志写 stderr，测试进度和命令结果仍可使用 stdout；测试不读取其他项目配置，不调用真实模型、短信或支付，不连接业务库或 Redis。

| 实际命令／检查 | 结果 |
| --- | --- |
| `python manage.py test tea_saas.test_runtime_logging users orders support_ai.test_telemetry.AgentTelemetryTests support_ai.test_product_details --settings=support_ai.test_settings --noinput` | 53 项全部通过；其中新增日志测试 24 项，其余 29 项为受影响业务与遥测回归 |
| `python -m unittest tools.tests.test_redis_settings tools.tests.test_project_identity -v` | 5 项通过，保留已有 Redis 配置与统一命名 |
| MCP Python：`python -m unittest tools.tea_saas_mcp.test_server -v`，`TEA_SAAS_TEST_PYTHON` 指向业务解释器 | 9 项通过；包含 stdio → Django 命令 → 合成 SQLite，确认新日志不破坏 stdout JSON 协议 |
| `python manage.py check --settings=support_ai.test_settings` | 无问题 |
| `python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings` | No changes detected；没有执行迁移 |
| `python tools/module_versions.py check` | 15 个模块归属通过 |
| 10 份受影响 Python 的 AST 检查 | 通过；不单独视为业务验收 |
| `git diff --check` | 通过 |

共 67 项定向测试通过；前两组命令、退出码和记录见[测试摘要](tests.json)、[Django 输出](django-targeted.log)及[配置／命名输出](settings-and-identity.log)。MCP 结果来自本轮实际工具输出。没有重复执行整站回归，也不声称已解决历史 Agent 全量回归问题。

新增测试涵盖：原始消息、参数、附加对象、异常消息和缓存 traceback 不被输出；JSON／文本两种格式；Python warnings；默认与无效配置；格式化故障；不可写目录与轮转上限；响应头编号；HTTP 200 业务失败；路由模板及 404 隐私；一次未处理异常栈；框架返回后补记关联；大 JSON 和流不被额外消费；并发隔离；ASGI 适配；真实 OTel 根／子 Span；下一请求不继承 Trace；短信模拟、登录、注册与订单解析视图的敏感信息清理。

临时目录与 asyncio 测试在获准的本机隔离测试环境执行，避免已知 Windows 沙箱临时目录 ACL／socketpair 限制；未通过跳过断言或修改 Hook 完成验证。

## 本地运行检查

核实 8000 端口原本由本聊天创建的预览 PID 38160 占用后，重启该进程为 PID 36064，使新设置生效。仍为本机标准 WSGI 加静态文件处理，不是部署；关闭该临时预览器额外的原始 URL 请求行，应用中间件负责安全完成事件。

未修改私有 `.env` 或数据库目标，没有登录真实账号。运行以下不涉及业务写入的检查：

- GET `/login.html` → 200，日志 `outcome=success`。
- GET `/v1/users/session`，未附认证 → 401，日志 `outcome=client_error`。
- POST `/v1/users/login`，空 JSON → HTTP 200、业务码 10001，日志 `outcome=business_error`；参数校验即返回，没有查询账号。

三次响应均带独立的服务器 `X-Request-ID`，不采信测试提供的客户端编号；每个编号恰好对应一条 `http.request.completed`。结果见[HTTP 检查](live-smoke.json)和[安全日志样本](live-log-sample.json)。本地预览控制台由临时启动器重定向到私有临时目录；应用文件输出默认仍关闭。

## 限制

文件轮转只支持单进程本地使用，不提供多进程共享文件、按天清理或可靠持久化保证。普通日志不保存自由消息，第三方问题需按 Logger、异常类型和栈位置定位。静态服务／反向代理日志、终端评测报告及其他进程 stdout 不自动纳入本格式。

本轮不改变短信模拟接口包含验证码的原有开发响应，也未全面改写旧接口错误文本；它们不进入服务端日志。AgentSpan 数据库投影及现有导出开关继续沿用原方案；没有验证真实 Collector、模型或业务数据库就绪。
