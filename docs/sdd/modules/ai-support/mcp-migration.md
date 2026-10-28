# Agent 统一 MCP：全项目改造清单

2026-10-28实施前静态盘点，基线提交 `63fa850843771dde21c7bd49ed9bc98019e5d24a`。原盘点没有连接数据库、启动服务或执行真实模型。本页保留实施前差异与顺序，规则唯一正文为[Agent 数据访问规范](../../architecture/agent-data-access.md)。随后已按用户“运行”完成应用入口源码迁移，当前链路、保留职责及尚未部署的边界见[运行设计](mcp-runtime.md)，实际结果见[证据](../../evidence/2026-10-28-agent-mcp/verification.md)；下表不是当前未完成项的重新声明。

## 实施前架构

买家客服使用 `support_ai/views.py → workflow.py → tool_services.py`，经本地函数读数据。`views.py` 先直接读取历史和长期偏好，再把 `KnowledgeRetriever` 回调注入工具处理器。MCP Server 目前只提供 `get_product_details`，调用固定管理命令后复用详情业务函数；站内客服没有因此改为 MCP Client。

## 必须修改的运行路径

以下“拟新增”表示设计职责，文件名和工具名在实施契约中最终确定，不能视为已经存在。

| 优先级／范围 | 当前代码与问题 | 必需改造 |
| --- | --- | --- |
| P0 访问抽象 | `support_ai/views.py`、`workflow.py`、`tool_services.py` 没有统一 MCP Client；图还有旧 knowledge_search 路径 | 拟新增 MCP Client／工具注册及适配层；将数据型调用全部导向 MCP，图只消费验证后的 DTO。纯规划、来源校验、回答核验保留本地；正式切换不保留 LocalInvoker 或直接查询回退 |
| P0 服务拆分 | `tool_services.py:create_tool_handlers` 混合模型提取、来源证据、ORM、检索和回答 | 拆分宿主编排与可信 data_services；后端不接收 model 对象或任意 Python 回调，不把整个处理器搬成一个“通用执行”工具 |
| P0 私有授权 | `tools/tea_saas_mcp/server.py` 仅公共 SKU、固定子进程、无买家上下文 | 新增可信调用上下文的签发／校验、允许工具、对象归属、失效及重放约束；独立于模型参数。公开开发者入口不得因扩展而获得所有用户数据 |
| P0 结构与生命周期 | `server.py`、`support_ai/management/commands/mcp_product_details.py` 只有单工具 schema 和25秒桥接 | 扩展领域输入／输出契约、固定派发、错误映射、协议初始化、连接池／子进程回收、超时取消和有界重试；逐工具返回 DTO。先测量逐次启动开销再决定常驻服务 |
| P1 商品推荐 | `tool_services.py` 直调 `match_products`、`match_product_groups`、`recommend_bundle`；`recommendations.py` 和 `bundle_recommendations.py` 执行数据查询 | Agent 验证结构化意图后调用商品搜索／组合推荐 MCP；复用后端可售范围、属性筛选、分组、排序、整数分金额及组合约束。只实现平铺 search_products 不足以迁移全部推荐场景 |
| P1 隐蔽商品查询 | `tool_services.py:normalize_recommendation` 读 Catalog；详情追问读 SKU；`recommendation_explanations.py` 按旧名称补查 SKU 并读取实时商品 | 分类存在性校验、历史名称唯一定位和已展示商品事实刷新也移到领域工具内部或独立受限工具；不允许只迁移主推荐函数后保留这些 ORM 旁路 |
| P1 商品详情 | `product_details.py` 已被 MCP 命令复用，但站内处理器仍直接调用 | 将站内调用改走现有 MCP；保留后端函数。R06公开可展示／可售集合差异仍是独立待实现事项，不能因更换协议就声称缺货详情已支持 |
| P1 订单 | `tool_services.py:orders` 直调 `order_queries.py:query_orders`；`OrderQueryContext` 通过可变字段交接选中订单和导航；`context.py:current_order_context` 有旧适配 | 增加订单 MCP 和可信私有状态交接，保留服务端原话／引用核验、本人过滤、日期筛选、3／1／20分页及游标。宿主继续负责 commit_turn 和 HTTP 链接投影；旧适配删除或改用 MCP，不留下可调用旁路 |
| P1 长期偏好 | `views.py`、`preview.py` 直接调用 `context.py:saved_preferences`；此函数读 PostgreSQL BuyerMemory | 新增本人偏好只读 MCP；按任务必要／可选装配。拆开偏好 REST CRUD 与模型读取，两者可复用后端函数；不把无记录和故障合并，不允许模型自动写入 |
| P1 历史上下文 | `context.py:recent_context/context_from_turns/select_bundle_context` 从已保存轮次生成模型上下文和方案引用；HTTP 入口直接读取 | 新增本人会话模型上下文 MCP，保持24小时／6轮／6000字符、来源轮次和选择绑定。宿主只读会话控制元数据；用于模型的正文、推荐和对话状态均由 MCP 投影；请求内纯上下文整形可保留 |
| P1 知识检索 | `views.py` 直接创建 `KnowledgeRetriever`；`retrieval.py`、`retrieval_cache.py` 访问知识 DAO／版本及缓存；`workflow.py` 还有直接检索回调 | 新增知识 MCP，覆盖 scoped_search、证据、来源和 notes。复用 `ai_storage/knowledge.py` 的发布／ACL／向量空间、混合召回及重排。不得退化为裸向量查询，或把任意模型输入作为可见范围 |
| P1 检索预算 | `KnowledgeRetriever` 的 started、model_calls、embeddings、audit 目前在请求对象内；改成每次子进程会重置 | 设计同轮 ledger／受控检索会话，共享 deadline、改写次数、检索预算、notes 与缓存；可选 Redis 等后端但须验证隔离和失效。文本改写模型宜留宿主通过 MCP 取得证据，不能把整个含模型对象的 Retriever 跨进程序列化 |
| P1 预览和当前评测 | `preview.py`、`management/commands/agent_preview.py` 及 `evaluation/` 部分直接装配偏好／检索或业务查询 | 当前版本 Agent 场景复用同一 MCP Client；合成测试通过注入协议传输运行。仅比较 DAO／切块的离线实验可直接用隔离库，必须标明不是 Agent 全链路验收；冻结历史报告不重写 |
| P2 观测与配置 | `configuration.py`、`model_client.py`、`telemetry.py`、`tea_saas/settings.py` 无统一 Agent MCP 运行配置 | 拟新增受控服务定位、解释器／传输、版本、超时和凭据引用；配置不可由用户／模型覆盖。记录 request／tool／耗时／状态／预算，不记录令牌、原始订单或私有正文 |
| P2 部署与依赖 | `tools/tea_saas_mcp/requirements.txt` 独立 SDK 环境；现有 `compose.*.yml` 主要部署存储、检索、OCR和Worker | 先确定受支持传输与进程隔离，再补宿主启动、服务健康／readiness、连接回收和故障观测。不要把 MCP SDK 直接塞进旧 Django 环境；健康检查区分公共目录、私有业务与知识依赖，不使可选偏好故障阻断全站 |
| P2 测试与文档 | `tools/tea_saas_mcp/test_server.py` 只覆盖现有详情；客服测试大量注入本地函数 | 扩展协议、身份、DTO、预算及旁路防回归，更新当前运行说明、工具清单和必要 CAP 契约；不能仅 mock 本地函数就声称 MCP 已验收 |

`search_products` 的平铺搜索草案见[专项设计](search-products-design.md)；它只覆盖上述推荐迁移的一部分，分组／组合和私有上下文必须补充独立契约。不得将该草案的“不含长期记忆”理解为整个客服不再使用本人偏好；偏好由宿主经独立 MCP 工具取得并按现有来源规则处理。

## 保留职责，不应机械改成 MCP

| 项目部分 | 保留原因／需要检查的边界 |
| --- | --- |
| `support_ai/recommendations.py`、`bundle_recommendations.py`、`product_details.py`、`order_queries.py`、`ai_storage/knowledge.py` | 后端领域实现仍需要查询库；清理的是 Agent 对这些函数的直接依赖，不是删除数据能力。可提取到 data_services，但不复制两套筛选规则 |
| `support_ai/views.py` 的认证、会话元数据、重放、保存；`conversation_history.py`；偏好 CRUD | 应用控制及用户显式操作保持原授权；给模型使用的历史／偏好投影从中拆出，不能把整个 HTTP 请求都封为模型工具 |
| `goods`、`orders`、`inventory`、`pays`、`carts`、`users`、`supplier`、`engagement`、`logistics`、`news` 及 `admin_panel` 的普通业务 API | 不属于模型数据入口；维持所属业务事实与权限。MCP 后端必要时复用这些服务，不反向让交易核心依赖 Agent 或 MCP 可用性 |
| `ai_storage/pdf_pipeline/`、`vision/`、导入／Embedding／知识审核发布、`deploy/` OCR服务及知识 Worker | 可信导入管道负责处理文件与入库；OCR／视觉模型只接收限定页面和任务，不持有数据库连接。未来 Agent 查询其产出走知识 MCP，不能用任意路径工具开放原文读取 |
| `client/static/js/buyer-support.js`、相关模板及商品／订单页面 | 保留既有 HTTP DTO 时无需为协议迁移强制改界面；若增加部分成功、warnings或新引用字段则按相应业务规格修改，不将内部 MCP 配置暴露给买家 |
| 历史 `reports/archive/`、SDD evidence 和冻结基线 | 历史材料保留原状态；源码检索须与当前运行路径区分。管理清理、数据诊断和隔离实验不是面向模型的运行时数据入口 |

## 实施顺序与完成门槛

1. **契约和授权**：明确数据／控制边界，定义公共 DTO、私有上下文及结果交接、错误和全轮预算；冻结各阶段范围。先验证私有授权再开放订单／偏好／历史工具。
2. **公共基础链路**：建立 MCP Client、固定派发和数据服务层，先接通已有详情；再实现平铺、分组、组合和推荐解释，删除分类／名称补查旁路。验证新旧查询语义等价和调用延迟。
3. **私有上下文与订单**：迁移本人偏好、历史、方案选择及订单，保留短事务和既有对象授权；覆盖跨用户、分页、失败后恢复、幂等及 revision 冲突。
4. **RAG**：迁移完整受控检索，落地跨进程预算和证据缓存语义；覆盖发布 ACL、向量空间、混合召回、重排、补检与引用核验，复用 JSON／PDF 质量评测集验证质量不退化。
5. **统一入口和交付**：HTTP／预览／当前验收场景全部切换，移除 Agent 本地降级和旧直调路径；执行访问规范的 AC-AI-MCP-001 至 AC-AI-MCP-006，检查部署凭据和进程隔离后再启用。旧版本回退须明确撤销该架构符合性，不能自动隐藏回退。

以上顺序不代表已完成这些阶段。迁移默认无需业务数据搬迁；若私有结果映射或预算账本采用新表，单独设计 Migration，并在实际数据库后端的隔离测试库验证。实现时分别评估 core（工具／配置）、support_ai、ai_storage、web 的版本及 changelog；本次纯文档不升实现模块版本。

## 本次静态检查记录

已检查分支、完整工作区状态、Worktree 列表和实际 Diff；针对当前源码检索 ORM、连接访问、模型创建、工具装配及 MCP 注册，排除历史报告冒充运行代码。盘点时 HEAD 如上、工作区起始干净；未验证服务存活、数据库权限或真实数据行为。后续实施证据应绑定最终源码 SHA，不能以本页替代业务／协议测试。

文档检查结果：本次11份 Markdown 的85个本地链接均存在，6条规则及6项新增验收条件完整，代码围栏闭合、无冲突标记或行尾空白；`git diff --check -- docs` 通过。`python tools/sdd_refs.py RULE-AI-MCP-001` 能检索定义和消费者引用；`python tools/module_versions.py changed` 确认本次文档归 core。本轮检查期间工作区另有并行商品导入改动，本次未修改、暂存或验证该实现；纯文档不运行数据库或模型测试，未提交、推送或部署。
