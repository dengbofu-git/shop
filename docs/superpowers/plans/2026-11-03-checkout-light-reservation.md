# 轻量库存预留与单次结算范围 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. 以用户本轮确定方案为准；不执行技能示例中的自动提交。

**Goal:** 单次结算默认最多20种SKU，锁库存前拒绝超限；新普通在线订单固定预留900秒，保留原子拆单、幂等、付款／取消／到期与采购车清理不变量。

**Architecture:** PostgreSQL/default是订单、预留、幂等和清理任务事实源，Redis采购车仅意向。平台900秒有效策略覆盖持久化历史TTL但不批量改写旧配置或订单。最多20种的服务端解析与早期验证限定短事务持锁范围；保留仓库关联锁保护仓库状态。

**Tech Stack:** Python3.13、Django5.2、PostgreSQL16、Redis7、模板／原生JavaScript、Node测试。

**Spec:** [当前预留规格](../../sdd/modules/trade/stock-reservations.md)；本轮INV-CHECKOUT-LIGHT-20261103用户授权摘要。旧600秒及60—900可编辑条款由本轮固定15分钟决定替代，最终同步规格及ADR。

## Global Constraints

- 实现／验证授权；无Git提交、推送、PR、业务库迁移、策略回填、服务重启或发布授权。
- 保留主工作目录已有PG-only、登录Hash计数及外部web增量；使用现有开发分支，不新增工作区。
- 购物车不预留；quantity/reserved_quantity/available_quantity及SKU.stock保留；不新增Redis缓存／队列／库存分桶。
- 默认单次20种SKU可配置；不是总件数，重复SKU拒绝。超限提示：单次最多结算20种商品，请减少勾选数量后分批结算。
- 每单新预留900秒，提交后固定；原订单不延期。1800秒预算、3笔／300件／60000元等原额度均不扩大，跨商家累计。
- 上限内仍整批事务：任一失败无部分订单、预留或清理任务；同requestId重放不延长、不重复占用。
- 历史Migration不修改；真实行锁测试仅隔离PG，Redis只用隔离实例／合成键，不测试业务数据。

## Review Focus

- sku_list缺省/null/空列表必须按Redis实际已选集合；未选行不计，伪造价格／数量无效。
- 超限检查必须早于expire_orders及采购车清理／旧格式升级，避免拒绝请求仍锁库存或改采购车。
- 平台900必须覆盖已有600/300等策略；API/UI显示有效来源，不冒充商家回填审计。
- 多商家TTL在1800预算中逐单累计，三店拒绝；旧600订单仍按原截止计费和重放。
- 共仓关联锁不能盲目去除；并发ABC／BD争抢B、富裕库存、到期／付款和提交后释放锁均用真实PG证明。

### Task 1: 实际结算集合与早期额度验证

**Files:** 新增`orders/checkout_limits.py`、`orders/test_checkout_limits.py`；修改`orders/reservations.py`、`orders/checkout_views.py`、`orders/views.py`、必要时`carts/state.py`及对应测试、`tea_saas/settings.py`和`.env.example`。

**Interfaces:** 单一`checkout_sku_limit()`返回正整数配置（默认20）；`validate_checkout_size(items)`统一拒绝。预览返回`checkout_sku_limit`及有效期限；创建使用归一化实际集合验证，缺省列表不绕过。

- [x] 先写并在隔离PG／Redis运行20允许、21拒绝、配置覆盖、未选行／件数／重复／缺省列表、拒绝无清理及无库存锁测试。
- [x] 实现解析和唯一服务守卫；数量／金额／待付等非库存检查前移至首次账本锁之前；库存／占比最终判断留在锁内。
- [x] 保留原子订单／幂等／预留／清理任务与旧清理失败重试，重跑定向测试。

### Task 2: 平台900秒有效策略

**Files:** 新增`orders/reservation_policy.py`、`orders/test_checkout_policy.py`；修改`orders/reservations.py`的policy_for接入、`orders/checkout_views.py`策略API及既有策略测试。

**Interfaces:** 不可变有效策略快照，`ttl_seconds=900`，数量／金额／占比沿用店铺原值；暴露`ttl_source`、`ttl_editable=false`和历史`configured_ttl_seconds`供说明。PUT非900拒绝；其余额度仍需真实操作者和理由审计，不批量回填旧TTL。

- [x] 先验证现有600、自定义300、无策略新单必须900、旧截止／幂等不变、两店1800／三店2700、PUT边界。
- [x] 实现平台策略来源及API，明确历史配置与有效TTL；既有数据库不写，不新增仅为改默认值的Migration。
- [x] 根据实际接口复核前端只读TTL和本店额度审计。

### Task 3: 页面防御与提示

**Files:** `client/static/js/orderconfirm.js`、`reservation-checkout.js`、`reservation-policy.js`、`client/templates/merchant_inventory.html`及必要模板资源版本；相应Node测试。

**Interfaces:** 预览返回的真实配置驱动提示及成功响应长度校验，不能硬编码20；超限回采购车减少选择，不继续POST。商家显示统一15分钟只读；已有订单支付模式不套新行数上限。

- [x] 先写默认／非默认上限、SKU行数非件数、预览后变化及保留既有未付款恢复入口的Node失败测试。
- [x] 最小UI增量，保留外部web改动，明确多商家期限累计可能受原预算拒绝。
- [x] 跑相关及完整现有Node测试。

### Task 4: PG并发、生命周期及集成收口

**Files:** 新增`orders/test_checkout_light_concurrency.py`，复用／补充现有reservation、cleanup、pays及登录Hash测试；同步SDD、ADR、版本和证据。

- [x] 真实PG测试ABC与BD争抢B无超卖且失败方D无残留、富裕并发累计正确、固定顺序、事务结束后可另行取得锁、待付不持数据库锁。
- [x] 验证同requestId重放／冲突、付款／关闭竞态、900秒到期精确释放一次、已付不释放、迟到支付异常；采购车清理故障及期间新加购保留。
- [x] 独立审核，按发现修复；执行相关和阶段集成PG／Redis回归、Node、模型／模块／策略检查并绑定源码指纹。
- [x] 记录未启用业务库与Git状态，回收本次测试容器／网络；既有受保护工作区与其他WIP保持。

## 本轮结果

本地实现／隔离验收完成，详见[正式证据](../../sdd/evidence/2026-11-03-checkout-light/verification.md)。本轮测试资源已回收，旧工作区和其他WIP保持，业务库和服务均未改动；没有Git提交／推送或PR。
