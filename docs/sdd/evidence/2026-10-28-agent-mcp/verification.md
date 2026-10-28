# Agent 数据入口统一 MCP：实现与隔离验证

日期：2026-10-28。规范：[RULE-AI-MCP-001—006](../../architecture/agent-data-access.md)。实现说明：[MCP运行设计](../../modules/ai-support/mcp-runtime.md)。版本：support_ai 0.24.0、core 0.9.0。基线 HEAD：`63fa850843771dde21c7bd49ed9bc98019e5d24a`；本轮未提交，工作区源码指纹见[清单](implementation-files.json)，不能仅按 HEAD 复现。

## 实现范围

HTTP、PreviewSession、工具处理器和当前诊断入口的数据访问改为 AgentDataAccess → 真正的 MCP stdio → SDK1.29.1 → 固定持久 Django 命令 → 可信领域服务。覆盖商品／分组／组合、分类／名称补查、详情／推荐解释、本人订单、偏好、持久历史和受控 RAG；后端 ORM及PDF Worker、普通业务 API、认证／会话保存继续保留。

新增短时签名上下文、每轮独立后端、私有订单交接、序号／nonce、防重建 claim、预算预留／结算和 DTO 二次验证。普通推荐可不使用不可用偏好，明确偏好任务失败不保存；订单失败不取消独立推荐。协议损坏不回退本地查询，下一轮不复用坏会话。

## 实际命令与结果

业务解释器为本机现有 Django Python 3.9，SDK为仓库独立 Python 3.12；均使用既有依赖，不向 Django 环境安装 MCP SDK。下列测试不使用业务 MySQL 或真实客户问答。

| 命令／检查 | 结果与覆盖 |
| --- | --- |
| `python -X utf8 manage.py test support_ai --settings=support_ai.test_settings --noinput -v 1` | 最终265项通过，22.261秒；独立 SQLite 测试库，包含原有规划、商品／组合、订单、上下文、依据、预算和新增MCP边界。单元测试显式注入合成传输，不冒充真实协议 |
| SDK环境 `python -u -m unittest tools.tea_saas_mcp.test_server -v` | 最终12项中11项通过、1项按环境条件跳过；覆盖初始化、工具列表、输入、错误、超时及取消回收，并验证持久桥接业务故障后继续、超时后不重建状态。跳过的是旧公开详情的可选跨进程测试；新的完整跨进程验收另见下行 |
| 业务环境 `python -u -m tools.tea_saas_mcp.agent_integration --mysql --postgres` | 16项检查通过：真实stdio SDK＋持久Django后端＋临时MySQL8.0.46＋独立PostgreSQL测试库。覆盖历史、偏好、分类、名称、详情、平铺／分组／组合、解释、匿名订单及私有导航、知识ACL、另一买家隔离、HTTP重放和预览。外部模型调用0次 |
| `agent_integration --postgres` 前置检查 | 临时SQLite业务库＋实际PostgreSQL的15项检查通过；MySQL验收补充了实际SQL后端限制 |
| `docker ps -a --filter label=tea-saas-mcp-fixture --format '{{.Names}}'` | 无输出，验收临时MySQL容器已清理；PostgreSQL测试库由绑定随机名字的finally清理，命令成功退出 |
| 项目变更Python文件显式 `py_compile` | 40个项目文件通过，排除独立SDK的 `.venv`；不把依赖库源码当作Python3.9项目源码检查 |
| 导出的 `agent_schemas.json` 与 `export_agent_schemas.content()` 比较 | 一致；严格输入模型与SDK加载契约同步 |
| `python tools/module_versions.py check` | 16个实现模块、全部工作区文件有归属；本次只递增core与support_ai，保留并行商品导入的版本和changelog |

实际后端验收脚本在数据库初始化前断言目标：MySQL来自本次新建唯一标签、随机宿主端口、无挂载容器，固定合成数据库；PostgreSQL名字严格为本次随机 `test_mcp_<12位hex>`。容器使用已有镜像，不拉取；finally关闭连接、删除测试数据库并移除本次容器／匿名卷。正常业务数据库的配置不被写回或迁移。

PostgreSQL知识仅使用合成的公开已发布、本人私有已发布、他人私有和草稿记录。两位买家分别只能检索公开与自己的私有资料；不读取现有知识内容。Embedding端点被指向不可用测试地址，验证词法路线在向量故障时仍按ACL返回已有证据；未据此宣称本轮重跑了真实Embedding／重排模型的检索质量评测。

## 故障与修正记录

Windows沙箱中最小 `asyncio.run(asyncio.sleep(0))` 也阻塞，已停止该沙箱诊断进程；协议及实际后端验收经工具审批在沙箱外执行，目标仍受脚本的隔离断言约束。没有绕过数据库权限或改用业务库。

早期回归的3条旧断言按已确认规则修正：普通偏好故障不再整轮503，确定性任务不要求模型服务，以及缺MCP工厂是技术错误而非空知识。新增部分成功用例使用了只返回单一推荐的旧假模型，修正为显式有限任务计划后验证订单失败与推荐独立性；没有放宽业务断言。最终新增版本变化应409、身份／版本失败立即中断且不能按可选偏好降级的回归，265项全部通过。

MySQL隔离验收暴露了合成用户名超过实际11字符字段上限，已按源码缩短后重跑通过；不修改业务字段或历史迁移。一次过宽的Python3.9 `compileall` 误遍历独立SDK环境的3.12依赖，已改为仅检查实际变更项目文件，依赖源码未修改。

## 覆盖及未执行边界

| 验收条目 | 本轮证据与限制 |
| --- | --- |
| AC-AI-MCP-001 | HTTP／预览真实协议、工具装配回归和无本地降级测试通过；普通管理／Worker ORM不属于Agent入口 |
| AC-AI-MCP-002 | 业务失败后独立工具及下一轮恢复、协议超时／取消和安全错误已验证；未对实际服务做长时故障压测 |
| AC-AI-MCP-003 | 伪造／过期／重放上下文、异主咨询、停用买家、未投影字段及知识ACL覆盖；真实订单字段不进入模型工具结果 |
| AC-AI-MCP-004 | 原推荐／组合／订单／上下文及知识算法定向回归通过；R06缺货展示、R09聊天序号映射及完整CAP界面仍未完成；JSON／PDF真实模型质量未重跑 |
| AC-AI-MCP-005 | 同轮Retriever状态、共享模型预算结算、坏会话隔离和HTTP重放覆盖；未进行多进程长时并发／容量测试 |
| AC-AI-MCP-006 | 实际MySQL＋PostgreSQL隔离端到端通过；Django宿主仍持有控制职责所需数据库配置，不声称操作系统级无凭据隔离或远程MCP认证已完成 |

本轮未新增Migration，未操作业务数据迁移、现有服务重启、远程发布、提交／推送／PR。无前端源码改动，不以Python语法检查代替浏览器验收。当前请求级进程冷启动的纯订单HTTP约5—8秒，幂等重放约数毫秒；这不是容量或线上SLA结论。

文档与范围检查：14份本次相关Markdown的123个本地链接存在，代码围栏、冲突标记、行尾空白检查通过；实际Diff已审阅，`git diff --check`通过。上述数字只统计本次文档，不包含并行商品导入文档。

工作区同时包含独立商品导入任务的源码、版本、SDD和证据，本次没有修改或交付其业务实现；共享版本文件保留双方增量。
