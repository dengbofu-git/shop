# LangChain 1.3配套升级验证

日期：2026-11-02。用户授权：升级LangChain至1.3并配套升级。源工作区分支codex/core-sdd-remediation，原HEAD 591a0ea721414ff33c0c4376282006543b213906；保留已有咨询历史菜单等未提交改动，未创建Git worktree或额外交付分支。

## 最终依赖

| 包 | 原版本 | 本次版本 |
| --- | --- | --- |
| langchain | 0.3.27 | 1.3.18 |
| langchain-core | 0.3.86 | 1.7.3 |
| langchain-openai | 0.2.14 | 1.7.3 |
| langgraph | 0.2.76 | 1.2.19 |
| langgraph-checkpoint | 2.1.2 | 4.3.1 |
| langgraph-sdk | 0.1.74 | 0.4.11 |
| langsmith | 0.4.37 | 0.14.17 |
| openai | 1.109.1 | 2.54.0 |

新增langgraph-prebuilt1.1.1、langchain-protocol0.0.20、xxhash4.0.2；LangSmith所需httpx2/httpcore2 2.16.0、truststore0.10.5和websockets17.4精确锁定。模型客户端仍使用httpx0.28.1。旧text-splitters0.3.11源码无引用，移出锁定并从本机运行环境卸载，避免core<1约束冲突。

Python3.13.18、Django5.2.18、Pydantic2.13.5及其他原有非AI版本锁定保持。无需业务Migration或知识向量重建。升级后现有模型适配无需生产代码修复；新增协议回归用于防止后续隐式切换Responses API或丢失usage。

## 实际命令和结果

所有Python命令均使用Python3.13。验证材料在本机忽略目录`.scratch/langchain13/`，不包含环境文件或凭据。

1. 官方PyPI JSON核对版本及requires_dist；独立venv安装最终requirements，`pip check`通过。
2. 原环境执行 `manage.py test support_ai.test_langchain_compat --settings=support_ai.test_settings --noinput`：1项通过，用于确认升级前协议基线。
3. 独立环境执行 `manage.py test support_ai.test_langchain_compat support_ai.test_cost_control support_ai.test_streaming support_ai.test_telemetry support_ai.test_mcp_tracing --settings=support_ai.test_settings --noinput`：56项通过。含真实SDK解析合成HTTP响应、thinking开关、结构化输出、max_tokens、Token预算、SSE最终结果和监控回调；无真实模型外发。
4. 独立环境 `manage.py test support_ai --settings=support_ai.test_settings --noinput`：336项，328通过、8跳过。第一次沙箱运行的本机LiveServer套接字被Windows拒绝（WinError10013），放行本机测试网络后完整复测通过；未修改业务实现来规避失败。
5. 实际本机运行环境应用相同锁定依赖，再执行上条完整回归：336项，328通过、8跳过。测试数据库均为SQLite合成隔离库，未读写业务库或调用付费模型；跳过项的既定条件不等于验收通过。
6. 两环境 `pip check`通过；`manage.py check --settings=support_ai.test_settings`通过。
7. `tools/runtime/preview.ps1 -Python .scratch/runtime-py313/Scripts/python.exe -Restart`：预检Python/Django及MySQL/PostgreSQL连接通过，本机页面HTTP200、MCP健康ready、workers=2、available=2。实际执行前服务未运行，原3306 MySQL master容器停止，已启动原容器；未更换数据库实例、迁移或修改数据。

原始本机日志：protocol-tests.log、agent-tests-unsandboxed.log、runtime-agent-tests.log、startup.log。首次默认镜像下载停滞后换官方PyPI；原运行环境无pip模块，使用隔离pip的`--python`安装，不替换解释器。install-report.json为初次宽松解析（包含SDK3）的探索记录；最终版本以根锁定文件及runtime-versions.json为准，不能把探索报告当交付基线。

## 启用与未覆盖

- 已更新requirements/constraints、core0.14.0和support_ai0.31.0的版本及changelog；当前SDD链接运行依赖规格。
- 本机Web与MCP业务工作进程使用`.scratch/runtime-py313`新依赖，SDK隔离解释器保留原MCP1.29.1，不改其协议。
- 知识Worker源码下次构建会继承共用新依赖，但现有容器镜像未重建，本次不声称Docker内已升级。未验证Linux镜像构建。
- 上述升级回归阶段未进行真实DeepSeek调用或历史回放；随后用户单独授权的6次真实合成测试见[真实模型记录](real-model.md)。仍未进行真实历史回放或浏览器全面业务验收。
- 未提交、推送、创建PR、发布或部署生产。没有新增数据库迁移。
- 独立验证venv作为本机恢复材料保留，没有启动额外测试服务。旧依赖清单与升级前文件在`.scratch/langchain13/before/`；回退须恢复成套旧依赖（含旧splitters），不能只降langchain一个包。
