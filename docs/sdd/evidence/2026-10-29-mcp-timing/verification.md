# MCP 分段追踪验收与性能分析

日期：2026-10-29。工作区：`codex/support-ai-mcp`，基线 `c5b09f7d5ac3c5bd124028a8d4a870f438fce389` 上的未提交增量；support_ai 0.25.0、core 0.9.2。实现说明见[分段追踪](../../modules/ai-support/mcp-timing.md)。没有提交、推送、部署、业务迁移或重启，旧业务Trace不能事后补齐。

## 本次验证

业务解释器为本机现有Python3.9环境，MCP SDK使用独立Python3.12。测试启动器从已有本机环境装载配置，不复制、打印或入库凭据；以下隔离命令不打开业务数据库。

| 实际命令／验证 | 结果与边界 |
| --- | --- |
| `python -X utf8 -u manage.py test support_ai --settings=support_ai.test_settings --noinput -v 1` | 272项通过，23.652秒；合成传输／模型，隔离SQLite。包含新增父子图、同时间戳、有界截断、缓存计数、敏感属性、批量写入及损坏报告不影响工具的回归 |
| `python -X utf8 -u -m unittest tools.tea_saas_mcp.test_server -v`，独立SDK解释器 | 13项中12通过、1条件跳过，1.770秒；CRLF就绪握手、异常帧拒绝、每会话只启动一次、故障及取消清理。旧可选跨进程用例未设置环境变量；下行真实链路单独覆盖 |
| `python -X utf8 -u -m tools.tea_saas_mcp.agent_integration --postgres --profile-output .scratch/trace-analysis-20261029/synthetic-profile.json` | 16项通过；临时SQLite＋随机命名PostgreSQL；真实stdio、授权及知识ACL。Embedding不可用时保留关键词证据，错误节点保留；不将故障写成健康证据缓存 |
| `python -X utf8 -u -m tools.tea_saas_mcp.agent_integration --postgres --local-models --profile-output .scratch/trace-analysis-20261029/local-model-profile.json` | 16项通过；本机真实Embedding／CPU重排，数据全为合成；无外部大模型调用 |
| `python -X utf8 -u -m tools.tea_saas_mcp.agent_integration --mysql --postgres --local-models --profile-output .scratch/trace-analysis-20261029/mysql-local-model-profile.json` | 16项通过；临时MySQL8.0.46容器＋随机命名PostgreSQL；真实SDK／Django子进程、批量AgentSpan、同Trace父子图、根命中数、工具私有结果与幂等链路，资源清理完成 |
| `python tools/module_versions.py check`、`git diff --check` | 通过；本轮无Migration、前端或数据库结构变更 |
| 变更Python源码AST检查 | 16个文件通过；不将语法检查作为业务验收 |

最后两处计时边界／遥测指标故障保护调整后，另定向复验 `support_ai.test_mcp_tracing support_ai.test_mcp_data support_ai.test_telemetry`，35项通过、1.003秒（含最后新增的启动超时无签名输出用例）。原始本机日志保存在忽略目录 `.scratch/trace-analysis-20261029/`；共享测量摘要见[measurements.json](measurements.json)，源码指纹见[implementation-files.json](implementation-files.json)。这些性能样本没有经过部署或真实问答模型质量验收。

## 最后一组实际计时

单位毫秒。每个请求新建SDK和Django后端，在同会话内查询两次相同的 `green tea brewing`。数据库仅4条合成知识，其中2条对测试买家可见；存储向量为合成1024维值。该实验只验证执行耗时与ACL，不评估向量检索质量。模型服务未被重启，不能把首测值称为严格的模型冷启动。

| 阶段 | 新进程请求1 | 新进程请求2 |
| --- | ---: | ---: |
| 第一次MCP知识查询 | 5419.404 | 4286.613 |
| SDK启动／初始化 | 1706.654 | 1235.651 |
| 创建Django进程 | 14.610 | 11.646 |
| 等待Django就绪 | 3078.885 | 2464.356 |
| 两次Embedding合计 | 136.692 | 142.619 |
| 关键词召回 | 12.251 | 10.352 |
| 两次向量召回合计 | 22.057 | 21.309 |
| CPU重排，2个候选 | 276.635 | 261.368 |
| 同会话第二次查询，证据缓存命中 | 64.167 | 83.426 |
| 根Trace，包含两次查询及关闭 | 5605.674 | 4487.798 |

父子 inclusive 不能直接相加，表中根Trace与第一次查询是包容关系；更细的衔接间隙、授权、缓存epoch和序列化见原始节点。Windows时间戳可出现相同值，父子恢复按图依赖处理，不能仅按时间排序假定父先子后。

## 结论与后续优化

- 启动链路约占第一次查询86.6%—88.6%。应优先测量常驻服务／受控进程池与精简依赖加载的收益，继续保持每轮身份、nonce、DataSession、revision和预算隔离。当前只补充观测，没有把后端改为常驻服务。
- 本组SQL召回合计约32—34毫秒，Embedding约137—143毫秒。当前小样本不能支持先改SQL／索引，亦不能证明业务库规模下没有问题；后续用代表性隔离语料和EXPLAIN拆分连接与查询。
- 本机健康接口报告重排在CPU上运行。本组2候选约0.26—0.28秒；此前SQLite＋PostgreSQL组首测为1.601秒，第二个新进程为0.195秒。样本极少，可能受服务首次执行和系统负载影响；不能推导P95或承诺GPU收益。后续做候选规模和文本长度对照再决定迁移。
- 同会话证据缓存把重复检索降至64—83毫秒。实验使用LocMemCache，新进程必然丢失该缓存；生产配置为Redis，**本实验不能证明生产Redis跨请求缓存失效**。生产分析应查看实际cache.status并保留ACL／epoch／配置分区。
- 实际Embedding／召回／重排仍为既有顺序，未擅自调整检索语义、并行策略、模型设备或服务超时。遥测本身从逐Span写库改为整轮一次批量写入，已有测试验证写入次数。
- 原请求根Trace43.618秒、MCP37.689秒未被本实验重放。旧记录没有后端分段，分析器明确报告缺失，不能用合成新结果宣称已解释或修复那37.689秒。启用此版本后需采集同类新请求才能继续定位。

## 启动依赖探针

另在隔离settings下用 `python -X importtime` 只执行 `django.setup()` 和加载 `mcp_agent_data` 命令，不执行工具或数据库查询。单次测得 Django setup 846.138毫秒、命令加载972.224毫秒；后者的导入树中 `support_ai.cost_control` 累计438.034毫秒、`langchain_core.callbacks.manager` 累计321.620毫秒。累计值存在嵌套，不能相加。当前预算模块为了 `BudgetedGraph` 顶层导入Runnable，纯数据后端也因此加载LangChain／LangSmith依赖；可评估拆开纯预算契约和图适配，减少数据进程启动依赖。该探针额外启用importtime，不能与RPC ready值直接作差，也不是多样本性能结论。原始本机文件：`.scratch/trace-analysis-20261029/import-time.log`。

## 未覆盖

未部署／重启业务入口；未改业务数据库；未启用新依赖；未调用外部DeepSeek；未做容量、P95、并发压力或真实模型质量评测。未验证远程MCP时钟同步。现有平台详情200节点上限及后端每次160节点上限均需按缺失处理，不能视为无耗时。
