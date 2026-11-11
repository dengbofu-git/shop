# 自动账户偏好独立交付

2026-11-11。用户已授权实现、本机应用，随后要求推送并创建PR。本次为DELIVERY_ONLY，只提取既有自动账户偏好，不扩展业务。基线`0127466829e1c39c65de30f7cbdc244efdf3637c`。

## 范围

- ai_storage 0.9.0：账户状态、持久任务、审计及0005迁移，BuyerMemory按需兼容投影。
- support_ai 0.36.1：同事务outbox、逐轮明确喜恶提取、真实完成采购快照、来源时间和人工屏障、正负偏好软排序。
- web 0.42.0：六字段查看／编辑／清除。
- core 0.20.3：默认关闭设置，统一预览入口管理唯一偏好后台。

原主工作区独立任务、精准导航、RAG、支付、OCR及完整依赖启动增量保留原处。共享文件逐处提取，不复制混合现场。本PR不要求SupportTask或新的咨询契约；偏好GET保持主干响应结构，新增disliked三字段。本轮硬条件及24小时／6轮上下文保持。

## 验证

以隔离交付源码在专属tmpfs PostgreSQL16／pgvector上运行12个模块，233/233通过，20.977秒，Django检查0。195份源码测试前后摘要均为`847499c6ed3d33eac13ace0ad05b559bd85ec11902122b453577d534bcac757b`，无漂移。配置为stdio合成MCP、LocMem、dummy凭据及不可用模型端点，没有业务库或真实模型请求；测试库及自建容器已回收。原主工作区265项混合回归不计作本PR通过结果。

实际命令：

```text
python -X utf8 -B manage.py test ai_storage.test_auto_profiles support_ai.test_profile_behavior support_ai.test_profile_extraction support_ai.test_auto_profile_flow support_ai.test_budget_scope_semantics support_ai.test_colloquial_budget support_ai.test_cost_control support_ai.test_bundle_priority support_ai.test_bundle_optimizer support_ai.tests support_ai.test_mcp_data support_ai.test_streaming --settings=tea_saas.pg_test_settings --noinput -v 1
```

隔离目标由runner提供TEA_SAAS_PG_TEST_PORT／PASSWORD，仅本机临时使用；绝不能替换为业务连接。历史ai_storage0001—0004与main保持，0005与先前前进迁移验证的源字节相同（SHA256 `07c4a7b77bce8bddb225038e61ae967ec70c903d0cfa5113947e3afef78fcbd1`）。摘要见`validation.json`。

交付区已运行`python -m unittest tools.tests.test_runtime_backend -q`：10项通过；`node --test client/tests/profile-preferences.test.js`：3项通过。覆盖禁用不启动、迁移就绪、异源／多根／PID复用、锁、六字段往返、清空和失败保留输入；未启动真实业务服务或调用模型。

## 迁移与启用

新增`ai_storage.0005_auto_profiles`仅创建三表、索引与约束；历史0001—0004不改写，不回填业务档案或改变BuyerMemory列。新人工API也维护屏障，因此部署前必须先应用新迁移，即使自动开关false。

仓库默认`SUPPORT_AUTO_PROFILE_ENABLED=false`；启动器不自动迁移。启用后使用同一Python、源码与配置，检查单default PostgreSQL及完整迁移才启动后台；失败不报告完整就绪。关闭开关并重启会停止已归属后台，保留人工屏障。代码回滚和数据库恢复分别设计，不自动反向迁移。

先前已授权的本机备份、迁移、2个真实合成提取及网络HTTP／MCP结果见[启用记录](../2026-11-11-automatic-account-preferences-activation/verification.md)。它描述分离前主工作区，不替代当前PR验证，也不表示本次Git交付再次部署。

## 限制与现场保护

未进行本PR浏览器视觉或真实模型质量评测。两个样例不能代表准确率；复杂指代、讽刺及未知表达可能被保守拒绝。商品关键词沿用名称匹配，外部未反映退款不可感知。180天窗口、90天衰减、单账户快照上限及500条屏障容量按[规格](../../modules/ai-support/automatic-account-preferences.md)执行。

原现场恢复ZIP、精确hunk清单、私有配置和数据库归档仅存本机忽略目录。PR未合入时保留交付区及分支；原工作区核销另按本地收尾规则办理，不自动删除其他任务产出。

主干同步：提交前基线0127466；推送前远端已前进到0684929（PR36有界知识补查）。正常merge保留双方实现，版本文档冲突保留两边记录；依Hook要求对集成后的support_ai升至0.36.1。最终合并树验证另行补录，旧233项不冒充最终树结果。
