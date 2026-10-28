# MCP 迁移 PR 交付验收

2026-10-28。实现及初始验收见[验证记录](verification.md)，本页为用户要求“验收成功后推送PR”的独立交付收口。

- 已重新验收的实现提交：`bb65d3a009b0b5e136a8c1765935026dcff4cc01`。
- 同步主干：`412c7ed1a7206b49d2f9c5363b8110a0a52018c1`。
- 分支：`codex/support-ai-mcp`，目标 `main`。
- 最终模块版本：support_ai 0.24.0、core 0.9.1；core 0.9.1只记录合并主干的元数据整合，保留MCP 0.9.0与主干0.8.4历史。

## 范围与主干同步

原工作区混有商品导入任务，已在受管理的独立Worktree精确复制59份MCP相关文件；未提交原工作区或其索引。随后main合入PR #24，正常merge只在版本清单、core changelog和版本说明产生冲突，按双方已确认版本及记录合并；未修改业务实现、历史Migration或依赖语义。合并门禁要求core对新增SDD YAML递增版本，正常升为0.9.1，没有绕过Hook。

商品导入、goods／web版本及0012迁移已属于main，不是本PR新增内容。最终PR改动只涉及MCP源码、契约、回归及文档；此交付记录和指纹更新不改变已测运行代码。

## 合并后重新执行

工作区现有Django3.9与独立SDK3.12环境分开使用。私有运行配置仅由本地引导程序装入测试子进程环境，没有复制或提交 `.env`、密钥或Token。

| 检查 | 结果 |
| --- | --- |
| `python -X utf8 manage.py test support_ai --settings=support_ai.test_settings --noinput -v 1` | 265项通过，37.724秒；隔离SQLite与合成传输 |
| SDK环境 `python -X utf8 -u -m unittest tools.tea_saas_mcp.test_server -v` | 12项中11项通过，1项可选旧跨进程用例条件跳过，2.696秒 |
| `python -X utf8 manage.py check --settings=support_ai.test_settings` | 0项系统问题 |
| `python -X utf8 -u -m tools.tea_saas_mcp.agent_integration --mysql --postgres` | 真实MCP＋临时MySQL8.0.46＋随机PostgreSQL测试库，16项通过，外部模型调用0，cleanup=completed |
| `python -X utf8 tools/git_policy.py verify --base origin/main` | 实现提交59份差异、16模块、40项Python/JS语法通过；补充本交付文档后，推送前在最终SHA再次执行 |

以上证据绑定实现提交；后续仅提交本文及指纹／引用元数据，最终源SHA和门禁结果记录在PR正文。源码指纹见[清单](implementation-files.json)。

## 交付边界

没有新增Migration、执行业务库迁移、重启已有服务或部署。没有重新做真实模型质量、浏览器视觉、长时并发或容量验收。请求级进程冷启动约5—8秒，物理凭据隔离及远程MCP认证尚未完成；保持既有运行设计说明。PR创建不等于合入或发布，远端保护状态未核实不作强制门禁声明。
