# 商家销售统计完整性提示 Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans；不得从本计划推导Git提交／发布授权。

**Goal:** 修正历史订单被CNY财务筛选后全零的误导，披露纳入／排除数量，区分零交易、部分可统计和暂无可统计人民币交易。

**Architecture:** 保持原销售资格及订单写入语义，只提取共享状态谓词并新增商家只读sales_scope元数据；概览与销售洞察共用解释逻辑，不猜测币种或汇总未知金额。

**Tech Stack:** Django5.2/Python3.13、PostgreSQL16、原生JS及Node测试、既有商家模板。

**Spec:** 用户在[只读完整性诊断](../../sdd/evidence/2026-11-03-checkout-groups/data-integrity-followup.md)后明确要求“修正这个问题”。现有[金额规格](../../sdd/architecture/currency.md)及[概览](../../sdd/modules/merchant-operations/workbench-overview.md)保持交易保护边界。

## Global Constraints

- 本店归属、原查询周期、状态及CNY销售资格不变，不改历史币种、金额、状态、付款依据或Migration。
- sales_scope覆盖同一商家／周期内的状态合格订单，distinct订单计数；不把待付款、仅定金、已退货／取消子类型混入待核验数。
- 元数据为currency=CNY，status_order_count、cny_order_count、unknown_currency_order_count、other_currency_order_count及financial_state。
- unknown含NULL和空字符串，other含非空非CNY；status=cny+unknown+other。complete无排除；partial有CNY且有排除；unavailable无CNY但有排除。
- analytics挂载summary.sales_scope，insights挂载data.sales_scope；原数值字段保持原类型及语义。
- 完全不可计CNY但有排除时金额／均额不呈现为真实零，显示暂无可统计；CNY订单数保持实际0并明确范围。真正零交易保留0，部分可统计显示实际CNY金额及排除提示。
- 概览及洞察三语、错误／加载清空、账号和请求隔离继续保留。缺失／畸形元数据不得伪造完整性或排除数量，兼容旧接口须提示范围信息暂不可用。
- 只读真实环境核验；合成测试在隔离PG／Redis，不连接业务库试跑。没有数据库迁移及Git交付。

## Approaches and Decision

既有对话已确认币种缺失及展示误导。保留现有CNY财务值并只加一句固定提示不能说明排除规模；按未知币种直接恢复旧销售额会违反金额规格。采用服务端真实计数加页面完整性状态，不变更财务资格；具体字段与布局由实现者在上述边界内确定。

## Review Focus

- NULL／空币种与非人民币分别说明；无CNY不等于无历史订单。
- 部分CNY数据不隐藏可确认收入；已排除数不能泄露外店或周期外订单。
- 一个混合店铺订单在本店仅计1笔，购买快照优先于当前商品归属。
- 缺失／非法完整性字段不应抹掉错误、泄漏旧账号内容或默认为全量CNY。
- 调整只读统计，不会把状态记录补造为真实付款证据或产生新占位。

## Tasks

- [x] 后端：先添加历史NULL／混合／外币／无订单／归属／周期／子类型RED，再实现共享谓词和范围计数，隔离PG回归。
- [x] 前端：先RED再实现概览与洞察提示、不可统计状态、三语、旧接口降级和加载错误清空；完整Node验证。
- [x] 主控：绑定既有源码现场，模型／模板及相关业务验证，独立终审；同步orders／supplier／web补丁版本及SDD、正式证据。
- [x] 本地收尾：核对73业务表及唯一运行源，在本会话已授权本地最新版修正范围内重载唯一后端；不迁移业务库／不发布Git，实际GET核验并回收测试资源。

结果：[验收](../../sdd/evidence/2026-11-03-merchant-sales-scope/verification.md)及[本机加载](../../sdd/evidence/2026-11-03-merchant-sales-scope/activation.md)。55项最终后端、133项Node通过，独立终审建议边界补测已完成；业务数据及新增交易保留，测试资源已回收，无Git交付。
