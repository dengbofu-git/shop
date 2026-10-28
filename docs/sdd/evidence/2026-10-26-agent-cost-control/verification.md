# Agent成本控制实现与验证

日期：2026-10-26；模块：support_ai 0.21.0。

0.21.0为本次成本控制增量。收尾时共享工作区另有人民币预算澄清修正并已递增为0.21.1，相关版本和代码保留，未覆盖回0.21.0；本证据仅说明成本控制范围，具体受检源文件见source-sha256.json。

用户明确要求实现分阶段thinking、收紧知识修正、去除重复审核及每轮模型预算。本轮在已有开发分支codex/orders-merchant-isolation增量修改，保留原脏工作区；期间已有其他任务的0.20.4改动继续保留。本次无提交、推送、部署、Migration或生产数据库写入。

## 实现边界

- 意图规划、条件提取、查询改写、知识生成、支持关系核验、通用审核分别配置thinking与输出上限，默认均disabled。全局thinking字段保留兼容，实际策略以阶段设置为准；仅服务端环境/settings配置，没有改前端流程。
- 每轮模型调用最多8次、输入65536 Token、输出8192 Token；ContextVar隔离请求，线程锁预占，工具中创建的新客户端也消费同一额度。每次调用发出阶段上限与剩余额度的较小值。
- 输入用含schema的保守UTF-8长度预估，成功后回填usage；缺少usage/超时保留预占，不能当成零成本。结构解析失败仍记录已有usage。SDK隐式重试关闭；供应商超额记录实际值并停止后续模型调用，不承诺追回已发生费用。
- 适配层恢复DeepSeek文档要求的max_tokens字段。MockTransport验证了实际HTTP正文，不是只断言Python属性。
- 知识生成与语义核验保留；有有效结论则返回部分结果，不整批重写。只有存在校验错误且没有有效结论才允许最多一次修正。茶类说明仍按已核验类别范围解锁依赖推荐。
- 程序业务单元、已有完整核验记录的知识单元及固定错误消息直接组合，不重复通用审核；单独一个verified字符串不足以跳过审核。原文引句、来源范围、数字、隐私、主体和语义支持检查继续执行。未核验文字若审核失败或额度不足不得发布。
- 程序独立查询仍可在其他步骤模型额度耗尽后完成；依赖失败继续跳过。JSON新增model_usage只读预算诊断，预览status新增model_cost_policy；无提示词、身份或思考正文。

## 本次命令及结果

环境为E:\miniconda\envs\<LOCAL_PROJECT>\python.exe，使用support_ai.test_settings的隔离SQLite；HTTP均为MockTransport或业务测试客户端，无外部模型请求。

1. 定向验证：

```powershell
E:\miniconda\envs\<LOCAL_PROJECT>\python.exe manage.py test support_ai.test_cost_control support_ai.test_grounding --settings=support_ai.test_settings --verbosity 0
```

最终48项全部通过；包含阶段HTTP协议、max_tokens、默认/显式thinking、跨客户端额度、输入准入、输出剩余额度、超额止损、超时保守记账、解析失败usage、请求隔离、LangGraph线程传播、并发预占、独立工具部分成功、部分知识只生成/核验一次，以及未核验文字失败关闭。见[最终定向日志](targeted.log)。

2. 扩展回归：

```powershell
E:\miniconda\envs\<LOCAL_PROJECT>\python.exe manage.py test support_ai.test_cost_control support_ai.test_grounding support_ai.test_mixed_tea support_ai.test_task_tools --settings=support_ai.test_settings --verbosity 0
```

加最后一项防伪核验标记测试前共73项，71通过、2项失败；见[扩展回归日志](regression.log)。最后新增项包含在上述48项最终定向验证中。两项失败均在将本次改动文件恢复为开工备份的隔离副本中复现，见[改动前复现日志](baseline-failures.log)：

- test_budget_still_applies_to_knowledge_bound_groups：既有用例按旧美元基础价格期待仅绿茶；当前人民币基础价与参考换算下同时返回红茶，断言不匹配。
- test_order_followup_reloads_status_and_keeps_identity_private：既有断言读取旧status字段，当前订单投影使用order_status，触发KeyError。

没有为通过测试而修改这两处业务或旧用例，不能声称扩展回归全绿。

3. 修改的10个Python文件AST解析通过；本次文件git diff --check通过。模块清单及变更记录同步为0.21.0；新文件均位于已有support_ai归属路径，文档变更不单独升级其他模块。

## 未验证范围

未执行真实模型、100条付费复测、浏览器、生产MySQL/PostgreSQL故障恢复或并发压测。因此只证明程序预算与协议边界，不证明实际节省比例、真实回答质量或供应商实扣金额。旧100条报告继续作为优化前冻结快照证据，不能回写成此次优化后的实测。

配置及有效开关见[模型设置](../../../Agent监控与模型设置.md)，业务边界见[回答依据与事实一致性](../../modules/ai-support/grounded-answers.md)。
