# 运行日志与 HTTP 关联

更新：2026-10-19。用户在审阅四阶段改进方案后要求实施；本轮实现前两阶段，业务审计、集中检索、自动保留及告警仍为后续范围。

## 输出契约

`tea_saas.runtime_logging` 使用 Python 标准 logging，默认 JSON 行输出，支持文本模式。控制台始终开启；本地单进程可显式开启 `logs/application.log`，默认每份 10MiB、保留 5 份备份。多进程／容器部署使用控制台加外部采集，不能共同轮转同一个文件。

为避免未知第三方异常和日志参数泄露，采用正向字段策略：**不输出 `LogRecord.msg` 的自由文本、格式化参数、额外字典、请求对象、请求／响应正文、Header、SQL、异常消息或局部变量**。仅注册的固定事件名可以输出；其他日志记为 `application.log`，保留 Logger 和级别。Python warnings 经同一格式化器处理，记为 `runtime.warning`。

异常保留类型与最多 30 层栈帧的文件基名、函数名、行号；不保存源码行、绝对路径或完整原始 traceback。当前被清理的事件覆盖注册、登录、短信模拟、订单收货／删除，以及客服、规划、检索和遥测失败。新增事件需登记 `EVENTS`，不能把用户内容拼接进事件名。

允许字段：`timestamp`、`level`、`service`、`logger`、`event`、`http_request_id`、`trace_id`、`span_id`、`method`、`route`、`http_status`、`business_code`、`duration_ms`、`outcome`、`error_type`、`stack`。时间为带时区的 UTC。

## 请求边界

`RequestLoggingMiddleware` 位于中间件最外层。每次生成新的 32 位十六进制 `http_request_id`，通过 `X-Request-ID` 返回，不信任客户端同名 Header；不复用 Agent 的幂等 `request_id`，也不改变现有响应 JSON。

路由只记录 Django 解析后的模板，例如 `v1/users/<str:username>/profile`。未解析或提前结束的请求记 `<unresolved>`；不记录真实账号路径、查询串、IP 或身份信息。方法使用受限枚举。

每次请求记录一个 `http.request.completed`。HTTP 5xx 为 `server_error`，4xx 为 `client_error`；较小的普通 JSON 响应若含整数 `code`，0／200 为成功，其余记 `business_error`；其他情况按 HTTP 状态判断。只检查最多 64KiB 的非流式 JSON，不消费流、不缓存或记录内容。大 JSON 或无整数 code 的接口不会额外解析业务结果；流式耗时只到响应对象返回，不表示整个流传输时长。

Django 未处理异常保留一次框架异常栈，完成事件只记录摘要；已有视图自行捕获的异常由其原有捕获点记录。重复的框架状态摘要被过滤。框架在中间件返回后补记日志时，可从服务端请求对象上的安全快照取回编号；ContextVar 在 finally 中恢复，覆盖同步和经 Django 适配的 ASGI 请求，避免跨请求串号。

## Agent 关联

真实执行 Agent 时，将当次根 Trace 绑定到请求上下文。执行期间优先采用当前活动的子 Span；HTTP 完成事件保留当次根 Trace。不会从响应 JSON 读取 trace_id，因此历史幂等重放不会被标记成新执行链路。OTel 停用或尚无 Span 时不伪造 Trace。

现有 `AgentSpan` 数据投影、隐私白名单、模型调用和会话协议保持原样；本轮没有改变 Trace 导出属性或创建新表。

## 故障与运行

日志目录在首次写入时创建；目录不可写或轮转失败时关闭本进程的文件输出，发出一次固定的 `runtime.log.failed`，控制台继续输出。格式化或控制台输出失败不回显原始记录与异常；控制台也不可写时只能丢弃该条记录。日志失败不改变订单／登录响应。

默认不设置文件按天清理，不自动删除 AgentSpan，不新增业务审计事务，不启用 Collector logs 管道或通知。采集端、文件权限、持久化与保留期需要后续部署配置；本轮不宣称实现持久化保证或完整审计。

配置和排障见[运行日志指南](../../../运行日志.md)，架构取舍见[ADR-0001](../../../adr/0001-runtime-logging.md)，本轮证据见[验证记录](../../evidence/2026-10-19-runtime-logging/verification.md)。
