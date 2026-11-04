# 本地后端启用：轻量结算与登录Hash计数

时间：2026-11-03 20:58（Asia/Shanghai）。本chat用户在实现／隔离验收完成后明确要求“重启后端”，授权本地启用；未授权Git提交／推送／PR、生产发布或业务库迁移。

## 实际启用

- 唯一运行源为主工作目录，分支`codex/core-pg-retirement`，HEAD基线`a864f909b57ab0a53d213472f6f317b09eb8ee4e`及已验收本地未提交增量。实现指纹`cc6b20489b2b0ad837cf4c74c95252e7806bb9b4c899c60d15c02550aaf1b3cf`与[集成证据](verification.md)一致。
- 通过正式入口`tools/runtime/preview.ps1 -Python .scratch/runtime-py313/Scripts/python.exe -Restart`重启Web8000及MCP18082，并重启同源30秒到期清理进程及知识Worker。全部后台启动隐藏窗口，未重建镜像、改数据库／Redis服务或启动旧工作区。
- 生效源码版本：core0.17.0、orders0.7.0、carts0.4.1、web0.37.0、users0.4.4。此前登录Hash计数修复随同主目录最新版加载；未在真实账号上执行登录写操作或创建测试订单。

## 启用前后核验

预检查为Python3.13／Django5.2、单PostgreSQL/default、无MySQL驱动、待迁移0、MCP活动会话0；失败时不会先停止旧服务。停止及启动均检查原PID／进程树／端口与Worker只读代码挂载归属，防止误停其他项目或启动第二份服务。

| 实际只读检查 | 结果 |
| --- | --- |
| 登录页、买家AI页、支付页、商家库存页GET | 全部HTTP200 |
| MCP `/health` | ready，预热worker2，活动会话0 |
| 买家结算预览GET | checkout_sku_limit=20、reservation_ttl_seconds=900、reservation_checkout_version=1 |
| 商家预留策略GET | ttl_seconds=900、ttl_source=platform_fixed_900_v1、ttl_editable=false |
| 店铺配置／旧订单expires_at指纹比对 | 启用前后分别一致；没有回填策略或延长历史订单 |
| 进程／端口 | 唯一Web8000及MCP18082，8873无监听；30秒清理进程和同源知识Worker在运行 |

本次只读业务探针没有调用可能触发过期释放的订单列表／付款接口，也没有提交订单、操作购物车、调用支付或外部模型；原有到期清理服务继续正常生命周期工作。Web日志包含正常请求及固定runtime.warning事件，未见启动失败；清理进程错误日志为空。

本机收据在主目录`.scratch/runtime-activation-20261103-checkout/`：`before.json`、`after.json`、`restart.json`及`closeout.json`。记录实际PID及时间，不包含Token、账号或凭据。业务数据库结构、持久化策略和历史截止未变，Git状态保持本地未提交；真实支付、模型质量和生产容量不由本次健康检查推导通过。
