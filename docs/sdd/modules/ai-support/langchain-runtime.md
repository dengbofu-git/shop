# LangChain 1.3运行依赖

2026-11-02本地统一收口：知识Worker已按同一锁定依赖重建，Web/MCP/Worker均使用LangChain1.3.18配套栈，pip check和公开ToolNode导入通过；本次启用及覆盖边界见[证据](../../evidence/2026-11-02-priority-activation/verification.md)。

2026-11-02用户明确要求升级LangChain至1.3并配套升级。当前规格采用1.3.18；保留已有StateGraph、有限意图提取、确定性模板和受控工具执行，不因依赖升级改用自主Agent循环。

## 依赖与边界

完整安装以根目录requirements.txt及constraints-py313.txt为准。配套锁定langchain-core1.7.3、langchain-openai1.7.3、langgraph1.2.19、checkpoint4.3.1、SDK0.4.11、langsmith0.14.17，OpenAI SDK2.54.0。

SDK2.54满足适配器的>=2.45约束，保留模型客户端现有httpx0.28传输及可模拟测试，不自动带入SDK3。LangSmith自身依赖HTTPX2，与模型客户端HTTPX并存，httpx2/httpcore2/truststore/websockets另行精确锁定。各包独立版本，不要求统一为1.3。旧langchain-text-splitters不再是直接或传递依赖，源码未引用；现有环境升级时须移除其旧0.3包，避免残留依赖冲突。

Python3.13、Django5.2、Pydantic2、数据库引擎、向量维度与嵌入/重排模型不变。不新增Migration，不重建知识向量。工具MCP SDK独立虚拟环境保持其自身依赖；业务MCP后端使用本项目升级环境。

## 模型协议验收

- DeepSeek沿用Chat Completions，不能误切换到OpenAI Responses API。
- thinking开关与json_mode/function_calling保持分阶段策略；结构化分片完成后才做Schema验证。
- max_tokens、stream_usage、输入输出Token统计和预算拒绝保持可观测；不得恢复SDK自动重试绕过调用预算。
- OTel回调、跨进程MCP统计、SSE最终权威结果和断连取消保持原契约。
- 使用合成HTTP MockTransport验证SDK请求与响应解析；真实模型评测需单独核对数据和调用授权，本次不外发真实历史。

安装依赖不会替运行中的进程自动换版本；本地后端与MCP业务进程需重启后核验。知识Worker镜像通过共用requirements/constraints在下次构建时使用新版本，未构建前不得声称容器已升级。实际命令、通过数量和运行启用状态见本次证据记录。

官方依据：[1.3.18发布信息](https://pypi.org/project/langchain/1.3.18/)、[v1迁移文档](https://docs.langchain.com/oss/python/migrate/langchain-v1)。
