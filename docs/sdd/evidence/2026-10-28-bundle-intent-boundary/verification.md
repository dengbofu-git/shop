# 总价套餐意图与购买规模修正验证

日期：2026-10-28。用户明确授权实现前一轮修正方案；范围为dadashop后续总价推荐行为。

## 改动

- 总价套餐复杂请求进入统一语义规划；总价新请求不自动继承历史茶类。模型新任务引用历史硬条件时检查本轮明确承接。
- 增加composition及quantity_policy契约，明确构成及自动配量授权须有用户原话证据；否定前缀不能被截去后用作授权。
- 工具入口统一复验，购买件数未确定也无自动配量授权则澄清，不读取商品，不返回自动凑量方案。保存预算及待补充状态，补充每款件数可继续。
- 普通预算按质量、较少件数、较少款数、较低总价及稳定标识排序；明确接近／用满模式仍按预算接近程度求解。明确多款至少两款，单款与款数冲突则澄清。
- MCP生成Schema同步；support_ai 0.25.0、core 0.10.1。既有未提交的商品导入、MCP迁移和运行基线工作保留，未提交或推送。

## 实际验证

Python 3.13 / Django 5.2，隔离SQLite和LocMemCache，不连接业务库。命令：

```powershell
& .scratch/runtime-py313/Scripts/python.exe -X utf8 manage.py test support_ai.test_bundle_intent_boundary support_ai.test_semantic_planning support_ai.test_budget_combinations support_ai.test_budget_quantities support_ai.test_total_budget_generic_tea support_ai.test_initial_budget_evidence support_ai.test_colloquial_budget support_ai.test_colloquial_budget_graph support_ai.test_budget_scope_semantics support_ai.test_mcp_data --settings=support_ai.test_settings --verbosity 0
```

结果：96项测试通过，Django系统检查无问题。最后运行输出在本机`.scratch/bundle-intent-fix-20261028/final-tests.log`。

覆盖：原问题进入模型分支、历史红茶不静默继承、明确历史承接仍有效、完整固定数量规则路径、缺购买规模时无商品查询、自动配量证据及否定校验、旧状态复验、普通／接近两种排序、明确多款限制、整数穷举排序对照、库存／金额及同SPU边界；合成模型决策→图→MCP协议测试传输→真实隔离商品查询→持久化→件数补充，以及明确批量用满预算。

MCP集成测试采用SyntheticMcpTransport和真实DataSession后端，不代表原生stdio SDK进程或生产MCP部署验收。模型响应为受控合成，不声称真实模型准确率或真实调用费用。此前34个失败断言及1个错误来自旧自动配量／套餐规则预期；已按新行为更新后纳入96项通过，旧反馈保留在本机compatibility.log。初始求解器7项旧排序失败也保留在tests.log历史之前的工具输出；最终回归验证了新的穷举排序和显式接近模式。

另外验证生成的agent_schemas.json与当前导出函数完全一致，授权文件git diff --check通过。

## 边界

未修改既有对话记录、业务数据库或历史迁移；无新数据库迁移。未运行真实付费模型评测、生产MySQL／PostgreSQL业务验证、浏览器验收或完整项目测试，未重启运行服务，未提交／推送／创建PR。
