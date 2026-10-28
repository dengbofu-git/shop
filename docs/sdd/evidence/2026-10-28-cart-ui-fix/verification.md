# 采购车图标同步与人民币默认显示

2026-10-28，用户报告卡片加入成功后图标滞后及购物车非人民币默认。web0.33.1，仅前端和说明修正，没有修改数据库或采购车金额。

原因：卡片成功处理遗漏data.carts_count同步；cart.js用浏览器buyer_cart_currency覆盖默认CNY。

修正：确认身份与成功回执后同步当前页#cart-count／.my_cart_count及AuthStorage缓存，按既有SKU种类数口径；无效计数不覆盖，存储失败仍更新DOM。每次进入采购车先以TeaMoney.base（CNY）初始化并记录，手动切换仍正常保存以供参考展示；旧币种不再覆盖新页面默认。模板脚本缓存版本20261028-cart-ui-fix。

实际命令：

```powershell
& 'E:\New Folder\node.exe' --test client/tests/buyer-support-cart.test.js client/tests/buyer-support-quantity.test.js client/tests/cart-currency.test.js
```

11项通过（其中cart-currency脚本含多组登录／游客、参考币种、选中及数量变更断言）。覆盖单品及整套立即同步、网络重试不重复添加、身份变化不覆盖、存储异常、无效件数、后端拒绝，以及旧USD／EUR／SAR／AED及非法币种均以CNY进入。参考币种切换不发送写请求，不修改原始商品金额，手动选择后本页选择／数量变化保留该币种。git diff --check通过。

未做已登录浏览器实点，不向真实采购车写入数据；不调用模型、不迁移、不提交或推送。

初次HTTP检查发现DEBUG关闭时模板缓存仍引用旧脚本；已由受管启动器重载本地服务，随后两页GET200且均包含新资源版本。没有改动DEBUG或全局缓存配置。
