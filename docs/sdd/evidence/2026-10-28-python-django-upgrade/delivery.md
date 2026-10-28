# Python／Django 升级交付复核

日期：2026-10-28。模式为 DELIVERY_ONLY，不扩展业务实现，不重放真实模型，不操作业务数据库迁移。

- 实现提交：`7202aab9b4a4ddf2a702067b5beb459b52cb195c`。
- 同步的 main：`3a8125fa610f656d2273010443e88a387c462bb9`；正常 merge 结果为 Already up to date。
- 交付分支：`codex/core-python-django-mr`，目标 `main`。
- 仅交付 Python 3.13.18／Django 5.2.18 及配套兼容调整。商品导入 PR #24 和 Agent MCP PR #25 已在基线内，不重新打包这些功能。

## 范围与现场

原主工作区停在 `63fa850`，有110条修改／未跟踪记录。逐文件核对最新 main 后，73个文件内容已在主干，33个文件属于本轮升级及证据，4个是本地旧证据与合入版的差异。4个差异位于商品导入与MCP验证资料，不是未交付的业务模块。本次没有还原、暂存、提交或删除原主工作区中的其他内容。

全工作区盘点发现9个已合并且干净的工作区；其存在不表示功能未合并。仍需核实占用后按仓库规则回收，不能以强删或清理脏文件作为提交前置步骤。新交付区只应用升级前后增量，保留 main 中已合并的代码、文档、模块版本和 changelog。

## 最终复核

验证使用最终 Python 3.13.18 环境，执行对象为上述实现提交的文件内容。后续本记录提交仅新增文档和证据，不改变已经测试的运行代码。

| 命令或范围 | 本次结果 |
| --- | --- |
| `python tools/git_policy.py verify --base origin/main` | 实现提交33文件，11项Python／JS语法检查，通过；最终文档提交后再次检查并在PR正文记录 |
| `python tools/module_versions.py check` | 16模块，所有工作树文件均有归属 |
| `python -m unittest tools.tests.test_git_policy tools.tests.test_module_versions tools.tests.test_project_identity -v` | 29项全部通过；已使用主干修正后的商品导入命名证据，未绕过检查器 |
| `python manage.py check --settings=support_ai.test_settings` | 无问题 |
| `python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings` | 无差异 |
| `python manage.py test orders inventory pays carts goods supplier engagement users support_ai --settings=support_ai.test_settings --noinput -v 1` | 509项，493通过、16按既有条件跳过 |
| 随机隔离MySQL库，订单预留／幂等／支付验签／商家订单／咨询评价／昵称／库存／商品导入 | 147项通过，测试库已清理 |
| 随机隔离PostgreSQL库，混合检索及pgvector | 11项通过，测试库已清理 |
| `python -m tools.tea_saas_mcp.agent_integration --postgres` | 真实本地stdio MCP链路16项通过，全部合成数据，外部模型调用0，测试库已清理 |
| Node及PDF／OCR模拟、Linux509项回归 | 复用实施阶段同一升级代码的结果；最新 main 同步后再次运行了上述受影响业务及协议验证；没有声称重新执行全部GPU或端到端浏览器验收 |
| Migration | 本次不新增、不修改、不删除任何Migration；已有`goods.0012`仍由原任务处理，不在此次交付执行 |

随机库MySQL命令：

```text
python manage.py test orders.test_reservations orders.test_reservation_contracts pays.test_reservation_signatures supplier.test_order_actions engagement users.test_nickname inventory goods.test_product_import --settings=engagement.test_mysql_settings --noinput -v 1
```

随机库PostgreSQL命令：

```text
python manage.py test ai_storage.test_hybrid_search ai_storage.tests.VectorStorageTests --settings=pg_settings --noinput -v 1
```

`pg_settings`为本机临时隔离设置，数据库名随机生成，不连接业务库试跑。结构化结果、日志摘要与最终源码指纹见 [交付数据](delivery-validation.json)。实施阶段的原始 [源码清单](source-manifest.json) 继续保留，仅代表当时工作树，不冒充同步后的提交内容。

core 0.10.0、goods 0.7.2、support_ai 0.24.1、engagement 0.2.3、ai_storage 0.7.2；保留主干的core 0.9.1历史记录。数据库引擎、AI主版本与页面结构保持原值。推送和PR以实际远端结果为准；没有授权自动合入或部署。
