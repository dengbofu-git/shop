# 推荐卡片用户加入采购车验证

2026-10-28，用户明确授权按“模型提供建议、用户发起操作、后端决定是否成功”设计并实施。carts0.3.0、goods0.7.3、support_ai0.26.1、web0.33.0。

## 实现

- 推荐原本已有上架及可用库存过滤；本轮统一到goods.availability.sellable_skus，追加有效商家要求，与下单拒绝无商家／停用商家的规则一致。正价、启用仓可售量，无账本才回退SKU.stock。商品详情库存来源改用共享查询stock_has_ledger，避免依赖已移除的旧聚合属性。
- 页面普通卡片可填件数后加入；套餐支持单行和当前整套，整套按钮显示总件数。动作位于详情链接之外；展示、切换方案和币种不写入。
- 新POST入口根据活跃本人买家、已保存SupportTurn请求及方案／SKU引用决定本次行与数量。整套不能由浏览器替换items/count，删除记录及他人引用拒绝。点击时再检查当前可售范围、保存CNY报价与累计库存；变价要求重新推荐。
- Redis Lua先校验全部行再追加，成功回执绑定本人＋操作UUID＋请求散列，24小时内重试不重复写入。旧单品POST共用原子追加并保留业务code；旧编辑CAS避免过期值覆盖并发数量。Agent和MCP不增加采购车写工具。

## 实际验证

Python3.13运行基线；数据库为隔离SQLite，不连接业务MySQL或PostgreSQL。新建本次专用redis:7.4.5-alpine容器（--rm、随机本地端口、禁用持久化），环境CART_TEST_REDIS_URL明确指向它。未使用业务Redis。命令：

```powershell
& .scratch/runtime-py313/Scripts/python.exe -X utf8 manage.py test carts.test_recommendation_cart support_ai.test_bundle_optimizer support_ai.test_bundle_intent_boundary support_ai.test_total_budget_generic_tea support_ai.test_mcp_data support_ai.test_budget_scope_semantics support_ai.tests support_ai.test_grouped_recommendations --settings=support_ai.test_settings --verbosity 0
& 'E:\New Folder\node.exe' --test client/tests/buyer-support-cart.test.js client/tests/buyer-support-quantity.test.js
```

后端114项通过、Django系统检查无问题；前端8项通过，无跳过。后端日志本机.scratch/recommendation-cart-20261028/backend-tests.log。购物车15项依赖显式临时RedisURL，未配置时会跳过，不能将跳过称为Redis验收。

覆盖本人权限、未登录、跨路径／跨记录、已删除历史、伪造SKU／方案、价格变化、下架／停用商家／无商家、禁用仓库存、已有件数叠加、整套失败无部分写入、重复UUID同内容／不同内容、成功后变价重试回执；真实Lua8并发同请求仅追加一次、8个独立请求不丢件数，以及旧编辑CAS不覆盖新追加。

前端执行实际cartAction函数及套餐渲染函数，验证展示不写入、用户点击绑定引用与可见数量、整套不提交任意items、网络重试保持UUID、重复点击不再提交、非法数量及后端拒绝反馈、原套餐大件数及金额校验。

扩展回归发现并修复商品详情的旧ledger_count依赖；有效商家夹具补充到受影响测试。此前0.25.1已将证据修复不足改为受控澄清，本轮同步过期503断言；仍验证技术依赖故障503且不新增提交，不在本轮改变该业务语义。

## 运行与限制

受管启动器核对身份后重启本地8000端口服务；实际GET buyer_support.html返回200且包含20261028-cart-actions资源版本，未登录POST新入口返回401。未向真实买家采购车写入验证数据，没有模型调用、订单或支付。未做已登录浏览器实点／视觉验收，也未运行全量项目或MySQL专属业务测试。

本次Redis容器6a681d9530f5710e273010fa278918343dd483bfe9018276df485372a9eb82cf已按精确ID停止，--rm回收。没有新迁移，不修改历史会话，无Git提交、推送或PR。其余既有工作保留。

Redis脚本的原子性针对本次追加；不构成数据库／Redis分布式事务，也不锁定库存。下单仍须复核。详细契约见[操作规格](../../modules/ai-support/recommendation-cart-actions.md)。
