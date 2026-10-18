# 确认订单验证

日期：2026-10-18；分支codex/users-unified-login，模块web0.15.0。实现见[规格](../../modules/trade/checkout-confirmation.md)。未提交、推送或部署，未修改业务数据库。

## 定向验证

- `node client/tests/checkout.test.js`：通过。验证187.51精度、十进制进位、无效金额／数量、三币种循环、按显示行合计、件数、选择地址后切换不丢失、不额外调用API、空商品禁用确认、存储受限，以及采购车／立即购买的原支付参数。
- `node --check client/static/js/orderconfirm.js`、`node --check client/static/js/checkout-utils.js`：通过。
- `python manage.py check --settings=support_ai.test_settings`：无问题；模块归属和Diff检查另行核对。没有改后端或Migration，未运行全量业务回归。
- `python client/tests/tea-saas-contract.py`：25个页面外壳、退役路由／资源和SDD映射检查通过；日志中的已退役页面404为预期。

## 浏览器

8019临时服务使用独立SQLite、合成买家和两条合成地址、四个SKU，采购车读取替换为内存数据；无业务MySQL／PostgreSQL／Redis连接。init.js在验收服务中改用当前origin，其余模板和脚本来自本次工作区。

- 合成买家真实登录后，确认页读取原orders.advance视图，商品合计$187.51、4款／4件，三步进度和两列内容正常。
- 选择第二条地址后，USD→AED→SAR→USD，金额分别为187.51／688.16／703.16／187.51，表头、单价和小计同步，配送地址不变。
- 通过新增地址dialog在隔离SQLite保存第三条合成地址，保存后自动选中且SAR显示保留；再选回第二条地址及USD。
- 没有点击确认付款按钮，没有创建订单或访问支付服务。没有实测窄屏设备、真实订单创建或真实支付；窄屏CSS已实现，不能替代移动端验收。

页面截图：[checkout.png](checkout.png)。验收后停止临时8019服务并清理对应SQLite，不影响原8000服务。
