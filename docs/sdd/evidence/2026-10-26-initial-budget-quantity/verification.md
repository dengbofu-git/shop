# 首轮预算与组合件数修复

2026-10-26；support_ai 0.23.1、web 0.31.8。工作区存在其他未交付任务，本记录仅描述本轮增量；未提交、推送或执行业务迁移。

## 问题与改动

- 原自动每款最多5件直接限制预算利用率。保留偏好优先排序，移除此限制，件数上界改为预算与当前可售数量；新增单款上界及有界双款整数方程种子，保留节点、时间和beam边界，不宣称全局最优。显式相同件数1—100仍按用户原值执行。
- 首轮unknown口径表示未确认，不需要肯定证据。普通预算不伪造额外cap要求；通用茶／茶叶不成为具体分类。模型选定新建单一推荐之后，保守补回遗漏的单一人民币金额并澄清口径；多金额、比较、旧价格等不据此宽泛查询。
- 当前字段证据缺项最多补正一次，仅替换失败字段的证据，不能重写金额、筛选条件或任务。原文无法证明口径可恢复unknown；记忆、历史和内部引用失败不能由补正绕过。归一化也不能隐藏这些来源错误。
- 卡片及保存引用允许安全整数范围内的大件数；网页继续核对单价×件数、行小计和方案合计，脚本缓存已更新。

## 本地验证

使用 E:/miniconda/envs/dadashop/python.exe，隔离test_settings数据库，不连接业务库试跑迁移：

```text
python -X utf8 manage.py test support_ai.test_initial_budget_evidence support_ai.test_budget_quantities support_ai.test_budget_scope_semantics support_ai.test_colloquial_budget support_ai.test_colloquial_budget_graph support_ai.test_total_budget_generic_tea support_ai.test_cost_control support_ai.test_semantic_planning --settings=support_ai.test_settings --noinput -v 1
```

最终79项通过，见[日志](final-tests.log)。包含双款整数解与小规模穷举比较、缺货数量限制、固定数量不被增加、千万件有界搜索、金额补全及来源越权回归。过程中发现的记忆来源补正问题已修正后复测，不把早期失败算作通过。

```text
node --test client/tests/buyer-support-quantity.test.js
node --check client/static/js/buyer-support.js
python tools/module_versions.py check
git diff --check -- <本轮相关已跟踪文件>
```

3项前端实际渲染函数VM测试通过，验证千万件显示、非安全整数拒绝及大件数仍须行小计一致；其余检查通过。未做浏览器交互视觉验收，未跑全量业务测试。

## 真实模型合成验证

用户分两次分别授权6条首轮合成问句、每题最多1次证据补正、每批最多12次DeepSeek调用。无真实历史、偏好或商品资料发送给模型。

- 第一批初测2/6通过、10次调用；使用剩余2次捕获同一失败题的结构化规划／补正，确认模型无原文依据同时生成cap和total。该批共12次，见[初测](real-initial.json)、[失败诊断](real-initial-diagnostic.json)。
- 修正后追加批次先4/6通过、8次调用；另2题被模型遗漏金额。放宽单金额保留检查的句式条件后，仅复核这2题，2/2通过、3次调用。追加批次总11次，见[复测](real-initial-retest.json)、[两题复核](real-initial-remaining.json)。没有再次全量6题同批运行；6题各自最近一次观察均通过，不将其视为生产准确率。

| 合成问句 | 最近一次观察 |
| --- | --- |
| 给出3000块的茶叶推荐 | 保留3000 CNY，口径unknown，仅缺budget_scope |
| 我想买点茶叶，3000元预算，帮我选选 | 同上 |
| 预算3000块，推荐茶叶 | 同上 |
| 帮我看看3000块能选哪些茶叶 | 同上 |
| 茶叶推荐一下，金额3000元 | 同上 |
| 我准备花3000块买茶，有什么推荐 | 同上 |

测试仅覆盖规划、提取、证据补正和分支校验，没有向模型发送商品资料或执行真实用户会话保存。最终源码额外增加了归一化不能隐藏非CURRENT来源错误的安全保护，79项本地回归包含该保护；真实合成调用不包含此类来源。

## 当前商品库只读检查

以合成3000元预算及绿茶／白茶软偏好调用实际recommend_bundle，未读取用户偏好、未调用模型、未预留库存或创建订单。实际三套均为3000元，见[只读结果](catalog-quantity.json)：75×40；75×37＋45×5；75×18＋66×25。这里只证明查询时当前候选可匹配，不保证未来价格、库存或其他预算均可恰好匹配。

## 边界

最多40候选、有界搜索、三套结果；三款以上不保证全局最优。价格是商品小计，不含未知运费税费。旧已保存回复不会被重写，重新提问才使用新算法。

本地noreload后端已从PID5412重启为2396，页面与脚本200，缓存标记和安全数量检查均已加载，见[runtime-check.json](runtime-check.json)。MySQL和AI PostgreSQL连接通过。启动仍提示其他知识工作对应的4份ai_storage迁移未应用，本轮没有执行这些迁移。未做部署或生产启用。
