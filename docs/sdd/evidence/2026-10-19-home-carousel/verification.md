# 首页轮播验证

日期：2026-10-19。范围为web0.18.0：首页轮播与现有语言、参考币种的接入。后端接口和数据库结构未更改。

| 验证 | 实际结果 |
| --- | --- |
| `node client/tests/buyer-carousel.test.js` | 图片、详情链接、参考价格、前后／圆点切换、RTL方向键、横滑不误跳转、纵向滚动、计时暂停恢复、单件、空列表、失败重试、过期请求、销毁与监听器清理通过 |
| `python client/tests/carousel-contract.py docs/sdd/evidence/2026-10-19-home-carousel/carousel-contract.json` | 隔离SQLite：实际接口返回6件、稳定排序、上架及库存过滤、商品名／价格／图片／链接字段；空结果与首页资源接入通过 |
| `node client/tests/buyer-carousel.test.js docs/sdd/evidence/2026-10-19-home-carousel/carousel-contract.json` | 使用真实Django视图响应运行同一组件测试通过；记录仅含合成fixture商品，不含业务数据 |
| `node client/tests/buyer-catalog-preview.test.js` | 首页分类10件分页、103件遍历、分类与语言保留等原回归通过 |
| `node client/tests/buyer-products-pagination.test.js` | 采购页分页与全部分类原回归通过 |
| `node client/tests/tea-saas-brand.test.js` | 三语品牌和看板契约原回归通过 |
| `node --check`（轮播、买家工作台） | 通过，语法检查不替代功能验证 |
| `python manage.py check --settings=support_ai.test_settings` | 无问题 |
| `python tools/module_versions.py check`、`git diff --check` | 模块归属与Diff空白检查通过 |

一次跨工具读取临时JSON路径失败，已改用上述固定证据文件并重新生成、验证通过；该次失败未作为功能通过证据。

未连接业务数据库或调用真实模型，未执行数据库迁移、浏览器视觉／真实触屏验收、Git提交、推送或部署。未覆盖的全站价格币种口径不在本次重定义。工作区其他任务的改动继续保留。
