# CAP-AI-003：回答前受限补查交接验收

2026-11-06，Asia/Shanghai。基线 `3fffc077229ff5ce6d62cfdc2410747a48f2ca49`，`codex/support-ai-bounded-rag-retry`，加本轮未提交差异，support_ai 0.34.1。主工作区 HEAD `f02a2a5`，有并行 WIP；开工时其检索、语义判断及定向测试三文件 SHA256 与基线工作树一致，本轮未改主工作区。基线既有验证记录不变。

复用规则优先、结构化选词、权限和截止时间校验、首轮证据保留、原题重排、缓存隔离和现有引用核验。补齐已选证据但语义判断未完成时的降级正文：保留经过核验的结论，提示覆盖未确认并标注 partial；没有结论仍用现有固定拒答。无新查询、调用额度、配置、迁移或 MCP 契约变更。

PG16/pgvector 0.8.7 一次性容器、随机 loopback 端口、合成环境、替身模型，复跑如下命令：基线 125 项、本轮 126 项通过，Django 系统检查无问题；两轮数据库及容器均已回收。加入回归断言后，原实现的超时/预算两个断言失败；新增正文用例首次亦暴露测试替身未支持原有 GroundingReview，已修正替身。

```powershell
python manage.py test --settings=tea_saas.pg_test_settings --noinput -v 1 support_ai.test_bounded_rag_retry support_ai.test_hybrid_retrieval support_ai.test_rag_coverage support_ai.test_cost_control support_ai.test_mixed_tea support_ai.test_grounding support_ai.test_mcp_data support_ai.test_mcp_tracing ai_storage.test_hybrid_search.KeywordSearchTests
```

独立配对重放：相同问题和首轮资料，开关各 20 次，6 组共 240 次。从知识工具入口经过真实补查编排、结构化模型接口、引用校验和答案核验；替换模型、召回和重排外部调用，关闭证据缓存。各组完整回答按预设证据项与核验后输出判定，不用 grounding 状态直接代替完整性。

| 场景 | 语义判断 / 旧改写（关→开） | 召回 / 重排（关→开） | 覆盖（关→开） | 完整（关→开） |
| --- | --- | --- | --- | --- |
| 简单红茶工艺 | 0/0 → 0/0 | 1/1 → 1/1 | 1/1 → 1/1 | 是 → 是 |
| 规则发现乌龙茶缺口 | 0/1 → 0/0 | 2/2 → 2/2 | 2/2 → 2/2 | 是 → 是 |
| 复杂对比证据够用 | 0/0 → 1/0 | 1/1 → 1/1 | 2/2 → 2/2 | 是 → 是 |
| 复杂题词面齐全、只讲红茶 | 0/0 → 1/0 | 1/1 → 2/2 | 1/2 → 2/2 | 否 → 是 |
| 同隐藏缺口，判断超时 | 0/0 → 1/0 | 1/1 → 1/1 | 1/2 → 1/2 | 否 → 否，开启时提示 |
| 同隐藏缺口，模型预算已用尽 | 0/0 → 0/0 | 1/1 → 1/1 | 1/2 → 1/2 | 否 → 否，开启时提示 |

合成场景完整率 3/6 → 4/6。逐组工具入口到核验返回的替身 P50/P95（毫秒）及调用数见交接目录的 `paired-followup.json`；不含 HTTP、MCP IPC、真实检索和模型网络。超时用立即抛出 TimeoutError 注入，默认 5 秒是配置上限，不是实测延迟。

## 真实模型实验复跑说明（待授权，未执行）

冻结同一公开合成知识快照、同一模型/配置/语言、固定 reranker/embedding、相同缓存条件。每条新会话和新请求 ID；关/开交错。至少每类 20 个独立配对题，并区分冷暖缓存、正常请求和注入故障。用人工标注的对象×主题×限定条件及出处判定证据覆盖、完整回答、正确部分回答和无依据陈述，不用“返回成功”作质量代理。

种子：①「红茶的加工工艺是什么？」一条直接资料；②「红茶与乌龙茶的加工工艺有什么区别？」首轮只出现红茶、乌龙资料可补；③同问，首轮两类工艺都讲清；④同问，首轮同段提及两者只写红茶工艺，另一条乌龙工艺仅补查命中；⑤同④，在独立测试网关仅给语义判断阶段注入超时；⑥同④，在隔离 Django settings 设 `SUPPORT_RAG_REWRITE_CALLS=0` 检验模型预算不足。先核查实际 trace 属于预设场景，不把未触发的样本计作覆盖。

用两套已按授权配置的隔离 Web/MCP 进程，启动时分别设置 `SUPPORT_RAG_SEMANTIC_RETRY_ENABLED=false/true`，两侧均开启既有检索及规则补查，固定相同数据快照，配置同一测试买家。以 JSON 响应结束为 HTTP 端到端耗时；计入失败请求并单列错误率。以下是单次请求模板，令牌通过进程环境提供：

```powershell
$question = '红茶与乌龙茶的加工工艺有什么区别？'
$body = @{message=$question;request_id=[Guid]::NewGuid().ToString()} | ConvertTo-Json -Compress
$elapsed = Measure-Command {
  $response = Invoke-RestMethod -Uri "$fixtureBase/v1/support/chat/" -Method Post -Headers @{Authorization="Bearer $env:RAG_TEST_BUYER_TOKEN"} -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body))
}
$elapsed.TotalMilliseconds
$response.trace_id
```

汇总每个场景/策略的 HTTP P50/P95、配对差值、调用次数、额外召回/重排、Token 与已核验完整率；trace 关联 `knowledge.query_rewrite`、`knowledge.retry`、`knowledge.rerank`。如先做无 HTTP 的公开范围冒烟，可在隔离环境分别设置开关后运行 `python manage.py agent_preview --message '红茶与乌龙茶的加工工艺有什么区别？' --json --log-dir <隔离输出目录>`，其 elapsed_seconds 不能当 HTTP 延迟。
经过复验的未提交代码及版本差异 SHA256：0D03A1B36D9218A11B9EF5230BE1999B08735F1C4234DE7DFE785E677C2DFD26
