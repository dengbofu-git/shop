# 商家预览及标签页身份验证

日期：2026-10-18；规则见[商家预览](../../modules/catalog-content/merchant-preview.md)。分支继续使用codex/users-unified-login；保留工作区其他既有改动，未提交或推送。

## 定向回归

- `node client/tests/auth-storage.test.js`：通过。两账号共享localStorage但使用独立sessionStorage；旧脚本写入共享身份后商家仍不变，空标签页不导入身份；刷新、同源iframe、独立退出和退出后不复活均通过。
- `node client/tests/merchant-product-preview.test.js`：通过。安全文本显示、售价／下架状态、关闭／再次打开、无购买控件和无买家详情跳转；实际商家脚本不含window.open或product_details.html。
- `node client/tests/unified-login.test.js`：通过，统一登录分流及运营初始化行为保持有效。
- 对认证存储、商家预览、商家商品和路由JS执行Node语法检查；模块归属及Diff空白检查另行核对。没有修改后端或Migration，未重复全量后端业务测试。

## 浏览器验收

临时8019服务使用独立SQLite文件、LocMem缓存与合成数据，未连接业务MySQL／PostgreSQL／Redis，也未使用真实账号密码。为本地端口适配，仅在测试服务器的init.js响应中将baseUrl设为当前origin；其余模板及JS使用本次工作区文件。

1. 商家merchant_t1登录后进入商家工作台；打开商品管理并点击下架SKU的“查看”，在原iframe内显示只读商品弹窗，顶层URL仍是merchant_dashboard.html，账号仍为merchant_t1。
2. 另一个独立标签页登录buyer_t1；刷新商家标签页仍显示merchant_t1和对应店铺，商品列表能重新加载。
3. 买家在自身标签页退出后，商家仍能请求自己的商品列表，编辑页“预览”仍在商家工作台内展示保存内容，未打开买家页。

截图：[merchant-preview.png](merchant-preview.png)。未验证真实业务账号的浏览器密码登录、真实商品写入或移动端完整流程。测试完成后停止临时服务并清理本次临时SQLite。
