# CART-LOGIN-HASH-20261103：登录采购车计数

后续启用：2026-11-03用户明确要求重启后端，登录Hash修复随同主工作目录最新版加载，见[实际启用记录](../2026-11-03-checkout-light/activation.md)。以下未启用说明是原定向验收时点，不代表当前仍未加载。

日期：2026-11-03（Asia/Shanghai）。用户在概念说明chat明确要求转交本chat修复；本次仅本地源码、针对性验证和记录，没有提交／推送／PR／部署或重启服务授权。

## 根因与修复

采购车`carts_<规范用户名>`由`carts/atomic_add.py`以HSET存储，每个SKU占一个Hash字段。加购回执及删除接口用HLEN，SDD既有`carts_count`口径为SKU条目数，非总件数。登录此前使用GET并按整键JSON列表解析；正常Hash触发WRONGTYPE，被裸except吞掉后静默返回0。

`users/views.py`现改用`conn.hlen(cart_key)`，仍以数据库中的`user.username`构造键；空车0，不因各SKU购买件数改变而变化。捕获RedisError，连接／超时／类型错误时仍成功登录、返回0，不清空或迁移采购车；非客户继续不读采购车。

降级发出固定`users.login.cart_count_unavailable`事件，并在安全日志白名单登记；不包含账号、Redis键、凭据或异常原文。版本为users0.4.4／core0.16.1；没有模型变更或Migration。

两个既有登录测试替身同步为HLEN返回0。前端`login-portal.js`已有AuthStorage计数消费，无需协议或页面修改。订单／支付响应中的同名字段沿用订单总件数，匿名localStorage购物车及Hash字段内旧JSON游标兼容均未变更。

## 复现与验证

使用本任务独立Redis7.4.5-alpine容器、随机127.0.0.1端口、tmpfs数据目录，无业务挂载或持久卷；每项真实Redis用例使用随机合成账号键及精确回执键，只清理自身键。关系数据使用`support_ai.test_settings`的SQLite内存测试库；不读写真实用户购物车或PostgreSQL业务库。

| 实际步骤 | 结果 |
| --- | --- |
| 修复前：`manage.py test users.test_login_cart_count --settings=support_ai.test_settings --noinput --verbosity 2` | 11项中3项失败：条目计数0≠3、大小写规范账号计数0≠2、真实原子加购Hash登录0≠3；故障降级等8项通过 |
| 真实Redis关键夹具 | 3个SKU分别2／7／13件，加购回执为3而旧登录为0，稳定复现；修复后为3，改其中一行至99件仍为3，登录读取前后Hash内容不变 |
| 首次修复定向回归 | 同11项全部通过 |
| 安全事件补漏 | 独立审核发现未登记事件被formatter投影为application.log；新增隐私断言先失败，登记白名单后在最终回归通过 |
| 用户＋采购车 | `manage.py test users carts --settings=support_ai.test_settings --noinput --verbosity 2`，56项中55通过、1项PG Unicode专用测试跳过 |
| 最终相关回归 | `manage.py test users carts tea_saas.test_runtime_logging --settings=support_ai.test_settings --noinput --verbosity 2`，**80项：79通过、1项PG Unicode专用测试跳过**，0.628秒，退出0；本次新增12项全部通过，其中3项使用真实隔离Redis |

上述命令使用主目录Python3.13解释器，真实Redis用例通过显式`CART_TEST_REDIS_URL`绑定专用容器。原始日志存主目录`.scratch/cart-login-hash-20261103/`：`red.log`、`green.log`、`log-event-red.log`、`users-carts.log`、`regression.log`、`regression-final.log`。

首次80项回归曾在历史`RequestLoggingTests.test_unhandled_exception_stack_is_recorded_once_and_context_is_cleared`失败：随机请求ID恰含合成验证码`6472`，整行字符串断言误报。已只固定该测试的合成请求ID，再完整重跑上述80项通过；生产UUID生成及日志隐私过滤逻辑保持。失败日志保留，不以重试隐去失败。

审核无遗留Critical／Important／Minor。`git diff --check`、模块归属／版本、Python语法及现行命名由独立临时index验证；真实暂存区不变。最终任务源码指纹及原有改动保护清单在同目录私有收据。未重跑全项目PG／MCP／前端或真实模型评测：本次未改SQL、MCP、页面或模型链路，之前PG任务证据继续按其原快照阅读。

## 交付及现场边界

修改保留在主工作目录`codex/core-pg-retirement`；既有PG退役及独立支付页改动保持，未写入或删除受保护的临时工作区。测试Redis容器验证后正常回收，不触及其他Redis实例。任务收尾状态见`.scratch/cart-login-hash-20261103/closeout.json`。

当前Web／MCP／Worker均未为本次修复重启，不能将源码测试通过表述为已在线启用。没有Git提交、推送、创建／合入PR或生产发布。
