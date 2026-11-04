# 商家历史币种缺失的统计展示修正

本地后续加载：2026-11-03 23:05:07已重载唯一后端，实际同店GET及页面解释器确认94笔未知币种排除提示生效，原历史订单保持、后续新交易保留，见[启用记录](activation.md)。

日期：2026-11-03（Asia/Shanghai）。用户在[数据完整性诊断](../2026-11-03-checkout-groups/data-integrity-followup.md)后要求“修正这个问题”。基线HEAD `a864f909b57ab0a53d213472f6f317b09eb8ee4e`，主目录分支`codex/core-pg-retirement`及既有未提交增量保留。对应[实施计划](../../../superpowers/plans/2026-11-03-merchant-sales-scope.md)。

## 修正范围

- `orders0.8.1`提取共享销售状态谓词，再由原入口叠加CNY条件；原标准／试单／预售资格保持。
- `supplier0.4.7`在analytics的`summary.sales_scope`和insights的`data.sales_scope`披露同店同周期状态合格订单数、CNY纳入数、NULL／空字符串未知币种数、其他币种数及complete／partial／unavailable。按订单去重，购买快照、混店明细、本店归属和原周期边界保持；原财务字段类型及数值不变。
- `web0.38.1`通过共享三语解释器校验完整性数据，明确CNY标签，分别说明两类排除。无CNY但有排除时概览金额及均额显示“暂无可统计”；真实空店或已有CNY订单的真实零金额仍显示0，partial保留可确认的CNY金额；完成率27／107等履约值保留。
- 洞察空态改为“暂无纳入统计的人民币商品记录”，年度排除只作全局说明；月表保留真实已计入CNY金额及0，不从年度范围推断每个月缺失。元数据缺失／非法明确显示范围信息暂不可用，不伪造排除数。加载、失败、账号切换和旧响应隔离继续有效。

只改只读统计与展示，不更改历史币种、金额、付款依据、订单状态或库存，不新增Migration，不猜测历史金额等同人民币。三份SDD的历史验收快照保留，当前契约见[销售范围](../../modules/platform/sales-reconciliation.md#商家统计范围与完整性2026-11-03)。

## 验证环境与结果

独立内部Docker网络，PG16／pgvector0.8.7及Redis7.4.5为tmpfs、无主机端口、业务挂载或持久卷。复用既有无MySQL驱动测试镜像。当前跟踪／非忽略源码打包进Linux临时目录，不含私有.env、Git、.scratch或业务数据；测试使用合成账号及随机PG测试库。

执行器：主目录`.scratch/runtime-py313/Scripts/python.exe -X utf8 -B .scratch/merchant-sales-scope-20261103/run_tests.py <run> <labels...>`，内部使用`tea_saas.pg_test_settings`调用Django test。每批源码指纹保存为`*-source.json`。

| 检查 | 实际命令／范围 | 结果 |
| --- | --- | --- |
| 后端有效RED | `scope-red-valid supplier.test_sales_scope` | 11项、14处失败断言／子例，确认原接口缺sales_scope；首轮夹具超长错误不计行为RED |
| 后端首次GREEN | `scope-green supplier.test_sales_scope supplier.test_analytics supplier.test_insights orders.test_currency admin_panel.test_overview supplier.test_workbench` | 54/54通过，3.988秒 |
| 最终后端 | `final`，同上范围并增加零成交价CNY＋未知币种partial边界 | **55/55通过，4.318秒**，退出0且随机测试库正常销毁 |
| 前端完整回归 | 枚举`client/tests/*.test.js`完整路径后执行`node --test @testFiles` | **133/133通过，0跳过**，583.189毫秒 |
| 模型／模板 | `run_checks.py checks ignored`：Django check、makemigrations --check --dry-run、merchant_dashboard loader render | 系统检查无问题、No changes detected、商家模板渲染通过 |
| 独立终审 | 只读当前代码、契约及测试 | 无确定P1/P2；建议零成交价partial边界已在前后端补入并通过 |

前端先以原实现观察概览5项和洞察3项失败，再实施GREEN。最终覆盖本例94笔历史NULL、混合CNY／未知／USD、真正空店、明确CNY真零、订单币种优先、子类型状态、周期／外店隔离、购买快照、纯SELECT及持久值不变、三语、加载错误清空、安全文本和旧接口降级。

额外`integration orders supplier admin_panel inventory pays carts`的**230项测试断言全部通过**，但整个命令退出1：测试库销毁时两个遗留连接仍占用随机测试库。该批不记为命令成功，也未为此扩大修改交易代码；最终统计范围55项单独重跑已正常清理通过。首次夹具失败、集成清理错误及所有原始输出保留在主目录`.scratch/merchant-sales-scope-20261103/`。

尚未以浏览器完整视觉或真实支付流程替代上述测试；Node DOM夹具与模板渲染不等于人工浏览器验收。本次没有真实模型调用、真实交易写入或Git提交／推送／PR；本地唯一运行源加载和真实只读GET核验另记启用记录。

源码与策略：临时index验证完整现场，真实index未改，允许范围外原工作摘要保持；只有orders／supplier／web补丁版本递增。最终实现指纹`b51b633e52794413433bdfa7144789e9ac7f8e0ce17a92a92871aad97e39a5c1`，与55项最终PG批次全部Python／JS／HTML／CSS逐文件一致；未新增或修改历史Migration。
