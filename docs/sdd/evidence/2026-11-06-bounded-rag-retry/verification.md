# 普通知识问答单轮补查验证

日期 2026-11-06，Asia/Shanghai。实现模块 `support_ai 0.34.0`。语义补查需显式启用 `SUPPORT_RAG_SEMANTIC_RETRY_ENABLED=true`，默认沿用规则补查。

隔离用例重放红茶与乌龙茶同段出现、实际只解释红茶的情形。验证只补查一次且沿用身份范围，按原问题重排，保留首轮相关证据。覆盖补查无新增、决策超时、非法对象与查询、原问题限定、缓存命中、未解决缺口禁止写入完整缓存、简单问题与分茶类分流、回答和复核预算预留。最终核验按已获引用支持的结论处理缺口，能显示可核验的一侧及不足说明。

在一次性 PostgreSQL 16 与 pgvector 容器中，使用合成配置、Django 隔离测试库和替身模型运行以下回归，126 项全部通过，Django 系统检查无问题。覆盖真实 PostgreSQL 知识发布权限、公开／私有隔离、缓存修订与撤回回归。测试库及临时容器已回收。

```powershell
python manage.py test --settings=tea_saas.pg_test_settings --noinput -v 1 support_ai.test_bounded_rag_retry support_ai.test_hybrid_retrieval support_ai.test_rag_coverage support_ai.test_cost_control support_ai.test_mixed_tea support_ai.test_grounding support_ai.test_mcp_data support_ai.test_mcp_tracing ai_storage.test_hybrid_search.KeywordSearchTests
```

Python 3.13 项目环境中核对 11 个代码和测试文件的语法及模块归属，`git diff --check` 通过。首轮隔离启动缺少合成模型环境变量，已补齐后重跑通过。

真实模型配对质量、调用成本和端到端 P50／P95 待测。当前记录仅证明隔离回归；本地预览未切换策略。
