# Redis 运行配置与采购车认证

日期：2026-10-18。实现模块 core 0.2.2；配置变更不改变采购车、订单或库存业务规则。

## 配置规则

- 默认缓存使用 `REDIS_CACHE_URL`，缺省 `redis://127.0.0.1:6379/0`。
- 采购车使用 `REDIS_CARTS_URL`，缺省 `redis://127.0.0.1:6379/1`。
- `REDIS_PASSWORD` 以原字符串传入两路客户端，不拼接到 URL，因此独立密码中的特殊字符不需要 URL 编码；空值表示不提供共享密码。
- 两端认证不同时，可在各自 URL 中提供认证信息并将共享密码留空；URL 中的特殊字符需编码。
- 凭据仅保存在本地环境或被 Git 忽略的 `.env`，不得写入示例、报告和提交。重启 Django 后加载新配置，不更改 Redis 服务认证或清理既有数据。

## 问题与本轮验证

预览中的 `POST /v1/carts/<用户名>` 返回 500，后端日志为 `redis.exceptions.AuthenticationError: Authentication required`；原因是已启用密码的 Redis 与未认证的 Django 连接不匹配。

- `E:/miniconda/envs/tea_saas/python.exe -X utf8 -m unittest tools.tests.test_redis_settings -v`：3 项通过；仅使用示例环境及合成密码，无数据库或网络访问，覆盖默认 DB 分离、独立地址、空密码及特殊字符密码传递。
- `E:/miniconda/envs/tea_saas/python.exe -X utf8 manage.py check --settings=support_ai.test_settings`：系统检查通过。
- 本地 `default`、`carts` 两路客户端认证 PING 均通过。
- 实际 `CartsView` 加购视图使用桩商品／用户及唯一合成采购车键访问真实 Redis，返回 HTTP 200、业务 `code: 200`；核对 Hash 后清理且确认合成键已删除。未连接业务数据库，未写真实用户采购车。
- 已重启本聊天启动的 8000 端口 Django 服务加载配置；不包含真实账号浏览器加购、订单、支付、真实模型或全站回归验收。

配置详情见[环境配置](../../../环境配置.md#4-redis)。无需 Migration；未自动提交或推送。
