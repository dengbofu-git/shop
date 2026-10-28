# 本地库存预留启用记录

日期：2026-10-26。用户在审核实现与验证结果后明确回复“授权”，范围为备份、核对限定计划、应用本地迁移、启动后端与到期清理进程。没有提交、推送、PR、生产部署或真实支付授权。本记录承接[实现验证](verification.md)。

## 备份与迁移

启动现有本地MySQL容器master，未重建容器或数据卷。SQL预检确认MySQL8.0.27、60张InnoDB表、无其他活跃查询、116条库存记录无异常且预留量0。当前8000后端未运行，迁移期间未启动Web写入服务。

完整SQL备份保存在本机忽略目录`.scratch/stock-activation-20261026/business-before.sql`，1013934字节，覆盖60张表、6178行；SHA256为`5de49c45a050e306e536bdf9d37553be34676b44151fbc1039719d52b8f00242`。校验导出退出码、完成标记、建表数、文件哈希及导出前后逐表数据摘要，未执行恢复演练。备份含私有数据，不纳入Git。

审阅实际计划后，仅执行：

```text
python manage.py migrate orders 0005_reservationpolicychange --database default
```

私有运行器调用同一管理命令，仅允许以下三项正向迁移，全部显示OK：

- inventory.0002_auto_20261022_1741
- orders.0004_auto_20261022_1741
- orders.0005_reservationpolicychange

首次摘要核验检测到auth_permission、django_content_type增加，确认系Django post_migrate为5个新增模型正常登记5条类型和20条权限，改为分别核对原有行后通过；未重跑迁移、未自动回退或修写数据。最终57张原业务表的原有列逐行摘要不变，原有模型类型／权限行不变，新增4条库存约束均存在，目标计划为空。

现有20笔历史待付款不自动关闭或预留，原订单、商品、库存和账号记录保留。新受管订单及预留记录均为0，启用验收未创建业务测试订单。

## 服务与只读验收

实际执行`python manage.py check`，结果无问题。后台隐藏窗口启动：

```text
python manage.py runserver 127.0.0.1:8000 --noreload
python manage.py watch_stock_reservations
```

启动PID、日志和只读报告在本机`.scratch/stock-activation-20261026/`；两个进程为本机手动启动，没有设置开机自启或异常自动拉起。

使用当前本地配置验收：登录页HTTP200；default和carts Redis PING通过；买家本人订单、商家本店库存、预留策略接口均HTTP200；预结算返回reservation_checkout_version=1。接口只读，不提交订单或修改商家策略，不调用真实支付。

ALIPAY_SELLER_ID当前未配置，因此支付链接会按保护规则拒绝生成。真实商户配置和支付／退款联调尚未完成，本次未更改支付凭据。PostgreSQL及其他项目的数据库、缓存容器未迁移、重建或清理。
