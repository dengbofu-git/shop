# MCP 分段追踪与耗时分析

实现日期：2026-10-29；support_ai 0.25.0、core 0.9.2。沿用[统一入口规范](../../architecture/agent-data-access.md)的权限、预算和私有状态边界，实际验证见[本次证据](../../evidence/2026-10-29-mcp-timing/verification.md)。本页不表示业务服务已部署或重启。

## 追踪交接

HTTP／Preview 在历史和偏好预取之前建立 `support.chat`。固定欢迎／功能说明、认证失败及幂等重放维持原路径，不额外创建模型请求。

宿主在 `mcp.rpc` 范围内，把当前 Trace ID／父 Span ID 写入绑定 nonce、单调序号的签名私有输入。工具参数、模型提示和公开 DTO 均不携带这些内部信息。后端建立相同 Trace 的远端父上下文，内存收集现有 RAG OTel 节点，经签名私有输出交回宿主；宿主校验名称、白名单属性、时间窗口、父子图和计数后投影至现有 AgentSpan 与可选 OTLP。正文、原问题、凭据、订单私有状态均不进入遥测。

原开发者公开详情工具不增加买家授权；没有可信 Trace 上下文或关闭监控时不收集后端报告。每次报告最多160个 Span，截断保留祖先关系，RPC 显示 `agent.mcp.telemetry=truncated`；错误／缺失报告显示 invalid／unavailable／export_failed，不能把缺失当成耗时为0。报告损坏不改变有效业务结果。签名、权限或查询错误仍按原有边界处理。

后端不独立写遥测业务表，不另外向 Collector 发送同一批节点。宿主把整轮本地投影一次 `bulk_create`，减少逐节点数据库往返；OTLP 继续使用原有有界批量队列。整轮结束前后台看不到半成品 Trace；异常结束仍尝试批量落库。落库失败不影响回答。Web进程崩溃可能丢失尚未落库的本轮记录，不宣称耐久审计。

## 阶段与准确含义

| 节点 | 覆盖范围／衔接 |
| --- | --- |
| mcp.sdk.startup | 首次创建 SDK 子进程到初始化、工具发现结束；同会话后续工具不重复执行 |
| mcp.sdk.spawn | 宿主创建 SDK 子进程的操作系统调用，不等于 SDK 已就绪 |
| mcp.initialize | 等待 SDK 导入和 MCP initialize 应答；包含 SDK 冷启动等待 |
| mcp.tools.list | 协议工具发现 |
| mcp.rpc | 私有输入交接、tools/call、签名输出读取与报告接收 |
| mcp.backend.spawn | SDK 创建固定 Django 后端进程的调用 |
| mcp.backend.ready | 进程创建完成到后端明确就绪；包含 Python 导入、Django setup、命令加载及授权会话初始化 |
| mcp.backend.call | 已就绪后端执行本次工具；启动节点与它为 RPC 的兄弟节点 |
| mcp.backend.authorize | 有效买家、咨询归属和 revision 复验；包含所需数据库首次连接 |
| knowledge.retrieve | 单次完整知识检索，包括证据缓存命中路径 |
| knowledge.cache | kind=evidence：知识 epoch／缓存查询；kind=embedding：Embedding缓存；status区分hit、miss、disabled、request_hit |
| knowledge.hybrid_ready | PostgreSQL混合检索结构探测 |
| knowledge.keyword_search | ACL限制的全文召回，包含连接、SQL和结果投影，非纯数据库CPU耗时 |
| knowledge.vector_route | 某轮第几个向量查询，包含缓存／Embedding与向量召回 |
| knowledge.embedding | 缓存未命中时实际本地模型HTTP调用，包含连接、排队、模型推理和响应解析 |
| knowledge.vector_search | 向量空间校验、ACL过滤、距离排序和结果投影 |
| knowledge.rrf | 候选融合及去重 |
| knowledge.rerank | 实际重排调用与校验；包含服务排队／模型加载等，不能直接视为纯推理时间 |
| knowledge.rerank.skipped | disabled、empty或request_budget；不计入重排服务调用次数 |
| knowledge.select_context | 实际证据选择、覆盖排序及字符预算处理 |
| knowledge.retry | 既有受限补检；内部改写、召回、融合及必要重排保留各自节点 |
| knowledge.query_rewrite / chat.deepseek | 后端受限改写及真实模型调用，Token／调用数汇总回根Trace |
| knowledge.cache_write | 健康证据缓存写入，不把服务故障写成负缓存 |

根 `agent.retrieval.hits` 按最终返回片段数累计，缓存命中也计数一次；它不是各路候选数之和，也不是答案最终引用的去重来源数。向量／关键词节点各自的 hits 只描述该路输出。后端模型与重排计数合并回根Trace，避免迁移前后的统计断层。

后端在就绪前崩溃或超时，无法返回签名报告；此时只能看到宿主 RPC 错误及 unavailable，不能虚构后端分段。当前以本机 stdio 的共同墙钟关联时间；未来远程部署需要单独设计时钟校正。平台原有Trace详情最多展示200个节点，完整本地投影可用下述命令分析；截断或丢失必须按缺失处理。

## 如何分析

在已配置应用环境下运行只读命令，不触发模型或重新执行问答：

```powershell
python manage.py analyze_agent_trace <32位trace_id>
```

输出包括各节点 `start_ms`、`inclusive_ms`、`self_ms`、按名称聚合、热点、缺失提示及待验证优化方向。`self_ms` 为节点总时间减去**直接子节点时间区间的并集**，并裁剪到父范围；并行子节点不会重复扣除。父节点包含子节点，不能把两者 inclusive 相加；独占时间也不等于纯 CPU 时间。未记录的内部工作仍留在父节点独占区间，不能仅凭热点名称断言根因。

## 优化顺序

1. 按实际 Trace 比较 SDK initialize、Django ready 与检索主体。启动占主导时评估常驻服务／进程池及依赖加载，必须继续每轮签名授权、独立 DataSession、deadline、预算、对象复验与清理；不能跨用户复用有状态会话。
2. 看缓存 hit／miss 和同一查询跨进程变化。生产使用配置的 Redis；隔离验收使用进程内缓存，两者不能互相推导。保留 ACL、知识 epoch、配置及向量空间键。
3. Embedding 慢时先区分模型首测／稳定服务、请求数量和缓存；可评估批量生成独立查询向量，保持每路候选和时间预算。不因一次快样本删除超时或补检边界。
4. 重排慢时记录候选数、错误／回退和服务设备。先做2／5／10／20候选及不同文本长度对照，再评估本地GPU、驻留与并发；本轮未改变服务设备或模型。
5. 召回SQL慢时才在代表性隔离数据上分析连接、EXPLAIN和索引；本轮两条可见合成片段的结果不能证明业务库容量性能。
6. 未覆盖的协议／序列化区间单独保留，不能强行分给 Embedding 或 SQL；原有历史37.689秒请求无法事后补出分段，也未用本轮合成结果宣称已修复该耗时。
