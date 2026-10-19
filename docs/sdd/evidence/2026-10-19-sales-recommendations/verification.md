# 推荐商品销量排序验证

日期：2026-10-19。模块：goods 0.4.3。规则见[采购页推荐商品](../../modules/catalog-content/sales-recommendations.md)。

## 变更与范围

`GET /v1/goods/recommended-products` 从全平台已上架、有库存的 SKU 中，按销量、更新时间、ID 降序取前 20 款；采购页继续显示前 6 款。人工推荐标记不再影响本区域，后台说明同步更新。保留原有库存口径、响应字段和智能客服排序。

未修改数据库商品、销量、库存或推荐标记，没有新增或执行 Migration。未提交、推送或部署。工作区其他任务的前端、Agent 和 Git 工作流改动保留，不属于本轮验证范围。

## 自动化验证

- `python manage.py test goods --settings=support_ai.test_settings --noinput`：退出码 0，运行 32 项，2 项 MySQL 专用用例在 SQLite 测试配置中跳过；其余通过。见[运行记录](goods-tests.log)与[命令摘要](tests.json)。测试使用隔离测试库。
- 新增 7 项测试覆盖多商家销量排名、未标记商品参与、库存及上架过滤、超过 80 个无库存候选、同销量稳定排序、双库存源及多仓去重、前 20 款限制和空列表。
- `python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings`：No changes detected。
- `python tools/module_versions.py check`：通过，15 个模块，工作文件均已归属。
- 本轮修改的 Python 文件 AST 检查和 `git diff --check`：通过。没有前端逻辑改动，未进行浏览器视觉验收。

## 实际 MySQL 只读核对

本地后端加载修改后，接口返回 HTTP 200、业务码 200、20 个 SKU，包含未标记推荐的商品。独立使用原有逐 SKU 库存函数过滤并按销量、更新时间、ID 排序后，结果与接口完全一致。详见[只读结果](live-mysql.json)。实际 MySQL 检查不替代隔离测试中跳过的两项其他用例。

当前业务库 104 个 SKU 的销量均为 0，因此本次实际数据只能验证同销量时的顺序和库存资格；非零销量的跨商家优先顺序由隔离测试验证。当前订单／支付／库存流程未发现自动累加 `SKU.sales` 的实现，不能将当前页面称为已具备真实销量差异的热销榜；本轮不回填销量或扩展订单事务。
