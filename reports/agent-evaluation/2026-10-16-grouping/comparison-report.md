# Agent 分类推荐优化对照

版本：support_ai 0.7.0 → 0.8.0。日期：2026-10-16。

## 原始问题与失败原因

> 那我希望你能根据不同的茶叶种类给我进行一些商品推荐，并给出理由

旧终端日志保留三次相同问题的失败，耗时分别为 2.594、2.519、2.326 秒。
诊断回放确认：`required.categories` 返回 6 项，而继承的偏好结构最多允许 5 项，抛出 ValidationError，最终被包装为 RuntimeError。
旧计划只保留“推荐”，没有形成按茶类覆盖的任务。

## 最终真实环境回放

原问题使用相同的两轮脱敏上下文开始，后续使用实际生成的回答继续对话，无人工替换模型或商品结果。

| 场景 | 验收结果 | 耗时 | 模型调用 |
| --- | --- | ---: | ---: |
| 原问题及原两轮上下文 | 六大茶类各 1 款，完整保留任务与理由 | 1.001s | 0 |
| 继续重复原问题 | 六大茶类各 1 款，无异常 | 0.965s | 0 |
| 第二类的商品多少钱 | 正确定位红茶，读取当前价格及库存 | 6.429s | 3 |
| 第六款商品多少钱 | 正确定位黑茶，读取当前价格及库存 | 5.130s | 3 |
| 推荐两款绿茶 | 返回两款绿茶 | 0.832s | 0 |
| 每份不超过 15 USD，排除红茶 | 其余五类各 1 款，所有单价不超过 15 USD | 1.198s | 0 |

六个定向场景通过，均未发生合规拦截。两个商品追问实际调用当前配置的 DeepSeek 服务；其余四个场景使用有界规则直接读取真实商品库。
相同原问题的两次成功平均耗时 0.983 秒。旧版失败耗时不能当作成功回答的性能基线，也不据此宣称整体系统加速比例。

## 本地自动化验证

81 项隔离自动化测试通过，包含原有回归及本次新增的分类条件、偏好数量保持、原文依据、数量歧义、预算和排除、无匹配、部分工具失败、模型条件校验、12 个商品引用、第二类多商品消歧、实时价格变化及历史字符预算。

```powershell
& E:\miniconda\envs\dadashop\python.exe -X utf8 manage.py test support_ai.tests support_ai.test_planning support_ai.test_task_tools support_ai.test_grouped_recommendations support_ai.test_telemetry --settings=support_ai.test_settings --noinput
```

使用 SQLite 内存库和 LocMem 缓存，不在真实 MySQL 创建或清空测试库。最终记录见 `unit-tests-verified.log`。

## 数据保留与复现材料

- `before/`：修改前关键源码、原始终端失败日志及诊断；`sha256.json` 已逐项复核，未覆盖。
- `candidate-manifest.json`：最终关键实现文件 SHA256。
- `live-replay-verified.json`：最终代码的完整回放输入、回答、计划、商品、诊断及性能数据。
- `summary.json`：验收汇总与客户记录数量核对。
- `live-replay.json`：首轮实现记录，保留预算场景尚未修正时的澄清结果。
- `live-replay-final.json`：预算规则修正后的首次完整通过记录，保留不覆盖。
- `unit-tests.log`、`unit-tests-final.log`：早期 77 / 79 项测试记录，保留不覆盖。

真实回放前后均为 16 条客户问答、6 个客户会话、118 条 AgentSpan。预览不提交客户会话，也不写运营监控；没有测试性改写商品价格或库存。单元测试中的价格及库存变化只发生在隔离内存库。

重复执行时使用新输出文件：

```powershell
& E:\miniconda\envs\dadashop\python.exe -X utf8 -u -m support_ai.evaluation.replay_grouped_preview --output reports\agent-evaluation\2026-10-16-grouping\new-run.json
```

该脚本拒绝覆盖已有输出，需当前 MySQL 和模型服务，使用保存的公开预览脱敏上下文。

## 口径与限制

- 这是针对已知问题的定向回归，不能解释为泛化意图准确率或推荐满意度达到 100%。
- 商品为当前数据库中的虚拟演示商品，属性中的“模拟”标签予以保留，不代表真实产地或检测认证。
- 推荐排序沿用偏好、推荐标记、销量及 ID；未增加基于风味或个人适配度的学习排序。
- 未识别的复杂条件继续调用模型并校验原文依据；无效条件返回澄清，不能绕过过滤推荐。
- 最多六组、每组四款且合计十二款；无货或查询失败可产生部分结果，数量冲突先澄清。
- 本地后端已重启，端口仍为 8000；运行中的旧终端需 `/exit` 后重启，通过 `/config` 的 `agent_version: 0.8.0` 确认。
