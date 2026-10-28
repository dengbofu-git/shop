# 客服订单跳转与简洁回复

日期：2026-10-26。模块：support_ai 0.21.2、orders 0.4.2、web 0.31.7。开发分支codex/orders-merchant-isolation；本轮未提交、推送或迁移数据库。

## 增量范围

- 每笔成功订单查询保存匿名查看链接；真实订单号只用于应用授权范围内HMAC计算。引用绑定买家，并使用字母编码避免历史号码脱敏破坏链接；只在模型和遥测完成后加入HTTP响应，不进入模型或工具事实。
- 新客服回复显示每笔“查看订单”链接，跳转buyer_orders.html并通过URL片段定位；原本人订单接口额外返回support_reference，页面仅精确匹配当前本人可见订单，提供“查看全部订单”。越权、隐藏或无匹配不能退回另一笔订单。
- 去掉近期三笔上限及要求提供订单号的固定尾注，查询时间继续保留结构化字段，正文不显示ISO时间串；保留状态以订单详情为准、分页下一页及付款到账核验等必要信息。
- 不改变下单、付款、试单／预售履约或状态解释；不是聊天内R09序号映射的完整实现。旧历史缺少引用时不根据日期／位置猜测补链。

## 验证

运行环境为项目conda Python与E:/New Folder/node.exe；所有问答均为本地合成内容，不调用真实模型。

- 首次7项后端定向测试：4通过、3因隔离LocMem缓存不支持既有OrdersView构造器中的Redis连接而出错；为测试替换该未被订单GET使用的Redis构造依赖，不修改业务Redis行为。
- `python -X utf8 manage.py test support_ai.test_order_navigation --settings=support_ai.test_settings --noinput -v 1`：7项通过。仅隔离SQLite默认测试库，未访问业务MySQL、PostgreSQL或Redis；Django配置检查0问题。
- 覆盖真实本人订单查询、匿名链接与订单列表一一对应、跨账号拒绝／不匹配、隐藏后失效、历史读取与幂等回放、保留付款不确定性及拒绝内容不附链接。
- `node --test client/tests/buyer-order-support-links.test.js`：3项通过；以合成已鉴权列表运行实际buyer-orders.js，验证精确定位、不可访问不回退、返回全部及同页新片段切换。VM模拟不是浏览器视觉验收。
- `node --check client/static/js/buyer-support.js`：通过。
- buyer-orders.js语法、5个相关Python文件AST、2份API YAML解析、16模块归属、定向git diff --check及5个新增／未跟踪文件行尾空白检查均通过。

## 本地加载

16:03重启既有8000服务，PID39532替换为17068；启动Django检查0问题。客服与订单HTML只读GET均200，包含20261026-order-links／20261026-support-link新缓存标记及返回全部订单按钮。保留既有ai_storage未应用迁移提示，未执行迁移；页面可用性不等于真实浏览器业务验收。

未进行真实模型、真实客户订单点击、浏览器布局验收或数据库迁移；全量模块／交易回归不在本轮范围。
