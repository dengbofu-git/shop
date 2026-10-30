# Agent 监控与模型设置

2026-10-19补充：普通运行日志已统一格式与隐私边界，HTTP 编号与当前 Agent Trace 可关联，见[运行日志指南](运行日志.md)。HTTP 编号不复用聊天幂等 request_id；本次没有启用 Collector 的普通日志采集管道。

平台运营入口：`/admin_panel.html` → **Agent 运行与设置**（`/admin_agents.html`）。所有设置、模型目录和监控数据接口要求登录且拥有 `system_config` 权限；停用账号、普通买家和普通商家无权访问。现有超级管理员角色已包含该权限。

## 安装与启动

使用统一的Python3.13/Django5.2环境安装 `requirements.txt`，通过[正式启动入口](Python与Django升级.md)运行。OpenTelemetry API、SDK和OTLP HTTP导出器固定为 `1.41.1`。

```powershell
python -m pip install -r requirements.txt
# 业务库连接应保持原 .env 中的配置，不要改成其他项目的 MySQL 实例。
python manage.py migrate support_ai --database default
docker compose --env-file .env.postgres -f compose.agent-observability.yml up -d
python manage.py runserver 127.0.0.1:8000
```

服务启动进程必须能访问配置的 DeepSeek 地址，以及本地 Ollama、PostgreSQL、MySQL 和 Collector。若启动进程继承了网络沙箱限制，模型会返回连接错误；修改 API Key 不能修复该权限问题。

在设置页启用监控和 OTLP 导出，Collector 基地址填写 `http://127.0.0.1:4318`。应用会分别追加 `/v1/traces` 和 `/v1/metrics`。HTTPS Collector 也可使用；认证 Header 通过服务器标准 `OTEL_EXPORTER_OTLP_HEADERS` 环境变量配置，或通过受控本地网关转发，不在后台页面输入或回显。

| 服务 | 本机入口 | 存储 |
|---|---|---|
| 平台 Agent 页面 | http://127.0.0.1:8000/admin_agents.html | 原业务 MySQL 的监控投影和配置审计表 |
| OTel Collector | http://127.0.0.1:4318 | 接收并转发 OTLP HTTP/protobuf |
| Collector 健康检查 | http://127.0.0.1:13134 | 当前采集进程状态 |
| Jaeger | http://127.0.0.1:16686 | 本地开发使用内存存储，重启会清空 Jaeger 自身的历史链路 |
| Prometheus | http://127.0.0.1:9091 | 独立 Docker 数据卷，指标保留 30 天 |

Compose 使用独立项目 `tea_saas-agent-observability`，所有主机映射端口仅绑定 `127.0.0.1`。Jaeger 内存历史不影响 MySQL 中的平台监控记录。生产环境需自行配置鉴权、持久化 Jaeger 存储和资源限制。

## 模型配置

### 0.21.0 分阶段成本控制

买家助手按阶段选择 thinking；以下阶段默认均为 `disabled`，优先于后台保留的全局 thinking 字段。可在服务端环境中设置，或由部署 settings 显式覆盖；不是聊天参数，也没有自动新增后台页面控件。进程重启后读取新的环境，单轮内冻结策略。

| 阶段 | 环境变量前缀 | 默认输出上限 |
|---|---|---:|
| 意图、语义规划 | `SUPPORT_PLANNING` | 1400 |
| 条件提取 | `SUPPORT_EXTRACTION` | 1600 |
| 检索查询改写 | `SUPPORT_REWRITE` | 512 |
| 知识及茶类生成 | `SUPPORT_KNOWLEDGE` | 2400 |
| 证据支持关系核验 | `SUPPORT_VERIFICATION` | 768 |
| 未核验文字通用审核 | `SUPPORT_COMPLIANCE` | 512 |

每个前缀支持 `_THINKING=enabled/disabled` 和 `_MAX_TOKENS=正整数`，单阶段配置最大8192；调用方已有更小上限时继续取更小值。例如仅复杂知识生成需要思考时，设置 `SUPPORT_KNOWLEDGE_THINKING=enabled`，不同时开启提取和核验。过小的上限可能导致结构化输出截断；技术失败不能当成可靠答复。

每轮共享预算默认如下，涵盖检索工具内新建的模型客户端：

| 环境变量 | 默认 | 配置范围 |
|---|---:|---:|
| `SUPPORT_MODEL_MAX_CALLS` | 8 | 1—32 |
| `SUPPORT_MODEL_MAX_INPUT_TOKENS` | 65536 | 1—262144 |
| `SUPPORT_MODEL_MAX_OUTPUT_TOKENS` | 8192 | 1—32768 |

输入按含结构契约的保守长度预占，收到 usage 后回填；输出以剩余额度与阶段上限的较小值发出。超时/缺少 usage 保留整个预占，不能解释成免费调用。输出超过供应商上限时记录实际用量并阻止后续调用；已发生的供应商超额无法撤回。SDK隐式重试为0，业务层允许的修正也必须重新申请同轮额度。本地 embedding/reranker 继续受既有检索预算约束，不记成外部聊天模型 Token。

知识默认一次生成、一次支持关系核验；只在有错误且没有任何有效结论时允许一次修正。有合格部分则直接返回并说明缺口。程序业务单元、已核验知识和固定错误提示不重复走通用模型复核；来源、逐字引文、数字、隐私、语义支持和依赖校验仍执行，未核验文字在预算耗尽时不得发布。

Agent JSON 响应的 `model_usage` 为预算诊断：调用数、阶段数、输入/输出记账、拒绝次数、未知用量及供应商超额次数。含未知调用时 Token 数是保守记账，不是实扣账单；不保存提示词或思考原文。终端预览 `status` 的 `model_cost_policy` 展示实际阶段策略，后台全局 thinking 字段不能单独代表本轮实际开关。

DeepSeek适配器会将LangChain改写后的字段恢复为文档定义的 `max_tokens`，避免只在Python对象上配置上限。协议参考：[DeepSeek Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)、[thinking开关](https://api-docs.deepseek.com/guides/thinking_mode/)。本轮只验证了模拟提供商请求和本地业务边界，实际降费比例需另做真实模型对照。

`SUPPORT_API_KEY`、`SUPPORT_BASE_URL` 保持在服务器环境中，不写入配置表、响应 JSON 或监控。模型选择通过当前服务器配置的 DeepSeek `/models` 接口读取，并在切换前再次校验。当前可用模型以该接口为准，不在前端写死模型列表。

数据库配置不存在或模型未覆盖时沿用 `SUPPORT_MODEL`。保存后，新请求读取同一份不可变配置快照，意图识别、专家回答、总结、合规节点使用同一模型；已在执行的请求继续使用原快照。已有 `request_id` 的幂等重放仍返回当时保存的回答。

思考模式可选择沿用 `SUPPORT_THINKING`、开启或关闭。DeepSeek 思考模式不接受当前结构化工具调用中的强制 `tool_choice`，因此开启时使用附带 JSON Schema 的 JSON mode 并进行 Pydantic 校验；关闭时保留原有工具结构化输出。思考模式单次调用超时为 60 秒，非思考模式为 20 秒，均允许 SDK 重试 1 次。

设置采用版本号检查，旧页面保存返回 HTTP 409，防止覆盖其他运营人员的修改。每次成功保存都记录操作者、时间和前后配置，不包含密钥。

## 监控含义

0.25.0：MCP后端启动、缓存、Embedding、召回、重排及补检已通过签名私有通道接回同一Trace；根统计合并远端命中数和模型用量。本地投影改为整轮批量落库。节点语义、只读分析命令和计时限制见[分段追踪](sdd/modules/ai-support/mcp-timing.md)。历史及偏好预取从该版本开始计入根Trace；旧Trace无法事后补齐。

使用手动 OpenTelemetry SDK 埋点，只采集 Agent 运行，不采集其他业务的请求正文或数据库参数。

- 根 Span `support.chat`：已通过认证和输入检查、实际执行的 Agent 请求。耗时包含执行图、推荐结果验证及会话提交，不含认证、输入检查、HTTP 传输或前端渲染。幂等重放不重复生成链路。
- 节点 Span：`agent.pii`、`agent.classify`、`agent.question_answering`、`agent.recommendation`、`agent.after_sales`、`agent.summarize`、`agent.compliance` 等。
- 0.6.0 当前执行路径为 `dialogue.resolve`、`agent.plan`、`agent.execute`、`tool.<工具名>`、`agent.compose`、`agent.compliance` 及 `agent.finalize`；上一条保留旧版节点说明。计划白名单属性含来源、任务类型与数量；工具属性仅含步骤标识和执行状态，不记录请求、结果正文。
- RAG Span：`knowledge.retrieve`、`embedding.bge-m3`、`knowledge.vector_search`，记录命中条数及异常类型。
- 模型 Span `chat.deepseek`：请求模型、服务返回的模型名称（可用时）、输入/输出 Token、耗时、错误类型。用量来自服务响应；未返回用量时按 0 记录，不估算费用。
- 指标：`agent.requests`、`agent.request.duration`、`agent.tokens`、`gen_ai.client.operation.duration`。Prometheus 名称会转换为下划线形式并补充类型/单位后缀。

SDK 的本地 SpanExporter 将完成的 Span 投影到 `AgentSpan`，平台按根 Span 聚合近 1 小时、24 小时或 7 天的数据，提供分页列表和父子节点时间线。安全拦截与执行异常分别统计：被合规节点拦截的请求仍可能成功执行。

OTLP 开启时，Trace 经 BatchSpanProcessor 导出，Metric 每 5 秒导出；Collector 转发至 Jaeger，并提供 Prometheus 抓取端点。导出失败不影响买家回答；队列有界且导出超时为 3 秒。平台展示当前 Web 进程最近一次链路/指标导出结果；多进程部署时，各进程在处理下一次请求时读取新设置，导出状态也各自维护。

监控只保存明确允许的运行属性，不记录问题、回答、推理正文、用户 ID、订单数据、请求 Header、API Key、异常消息或堆栈。页面展示 Trace ID 以便关联服务端链路，客户端响应也携带对应 `trace_id`。

本地投影默认不自动清理。按保留策略手动执行：

```powershell
python manage.py prune_agent_telemetry --days 30
```

该命令只删除过期监控 Span，不删除聊天记录、用户、配置审计、商品或订单。

## 接口与验证

平台接口位于 `/v1/admin-panel/agent/`：`settings`（GET/PUT）、`models`（GET）、`monitoring`（GET）、`traces/<trace_id>`（GET）。监控支持 `hours=1|24|168` 和 `page`，每页 20 条根请求。

```powershell
python manage.py test support_ai.tests support_ai.test_telemetry --settings=support_ai.test_settings --noinput
```

测试使用隔离的 SQLite/LocMem 配置，覆盖运营权限、停用账号、版本冲突、模型校验、审计、监控停用、链路父子关系、Token 汇总、隐私过滤及采集故障隔离。

参考：[OpenTelemetry Python 导出器](https://opentelemetry.io/docs/languages/python/exporters/)、[DeepSeek 模型目录](https://api-docs.deepseek.com/api/list-models/)、[DeepSeek 思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)。
