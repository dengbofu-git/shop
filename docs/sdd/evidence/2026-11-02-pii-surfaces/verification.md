# PII遗漏路径逐项复核

日期2026-11-02，Asia/Shanghai。用户要求“继续逐项处理”。实际分支codex/core-sdd-remediation，HEAD保持MR31源591a0ea721414ff33c0c4376282006543b213906；保留R08菜单、LangChain升级和上一轮PII全部未提交增量。本轮不计入问答题库，不自动扩展Git交付或部署。

## 逐项结果

| 项目 | 复现和根因 | 实现及验收范围 |
| --- | --- | --- |
| 历史/终端协议投影 | history_value/safe_record仍各自递归调用redact，对含连续数字的合法UUID产生不同于HTTP/SSE的结果，破坏会话/请求标识 | 两者直接复用redact_value，覆盖嵌套列表/tuple；合成固定UUID、邮件、商品编号、金额验证相同安全投影；原对象保持不变 |
| 无效模型工具调用 | AgentModel普通返回过滤content/additional_kwargs/tool_calls，却漏掉invalid_tool_calls内的原始参数和错误信息 | 返回前用统一策略处理该字段；实际适配器测试构造无效JSON参数中的邮箱及error手机号，验证不出适配器，不改原工具执行授权 |
| 字段语境 | 纯文本策略不能识别JSON整数手机号或receiver中的裸姓名，递归保持所有数值会放过显式联系信息 | 仅显式私人联系字段投影，电话号码/邮箱/实名/收件人/地址/证件等不因数值类型放行；不按通用name/id字段删除商品信息，sku_id/count/price及布尔标志保持 |

新增support_ai/test_pii_surfaces.py：3项测试先红（4个失败子项），最小修复后与test_pii_policy共15项定向测试全部通过。日志`.scratch/pii-surfaces-red.log`、`pii-surfaces-green.log`。使用合成数据，无业务库查询或历史批量更新。

## 验证

实际解释器`.scratch/runtime-py313/Scripts/python.exe`，Python3.13.18、Django5.2.18、LangChain1.3.18配套栈。

- `manage.py test support_ai --settings=support_ai.test_settings --noinput`：351项，343通过、8按组件条件跳过，无失败，21.289秒，日志`.scratch/pii-surfaces-full.log`。包含订单引用、跨账号与会话拒绝、知识/任务、保存/历史、模型协议、遥测及真实回环SSE；数据库仅隔离合成SQLite，未调用真实模型。
- `tools/tea_saas_mcp/agent_integration.py --resident`：19项通过，实际HTTP MCP SDK→预热Django进程池，临时SQLite业务/知识夹具；provider_calls=0、cleanup=completed，日志`.scratch/pii-surfaces-mcp.log`。SDK使用原独立解释器，后端使用当前实际解释器，无业务库或付费模型调用。
- `tools/module_versions.py check`：15模块归属通过；Django系统检查无问题；`git diff --check`通过，5份本轮Python AST及源码/日志哈希见source-snapshot.json。相关日志只保留本机忽略目录，不包含真实凭据或业务记录。

support_ai本地升至0.32.1，更新changelog及现行PII规格。此前0.32.0的样本对比和环境修复记录保留原时点；本轮不改写其哈希快照或重算旧证据。未提交、推送、合入MR31、迁移或重启服务；运行启用未验收。中文NER、URL内容、真实浏览器和完整业务AC仍按现有边界，不用本轮通过数量宣称已全部完成。
