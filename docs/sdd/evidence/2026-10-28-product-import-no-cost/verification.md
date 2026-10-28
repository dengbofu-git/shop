# 商品导入移除内部进价字段

2026-10-28（Asia/Shanghai）；CAP-CAT-002／FEAT-005，商品导入规格0.1.1。用户指出进价属于商家内部业务，本轮将其从通用商品导入合同移除。goods0.7.1、web0.32.1；工作区和源码指纹见manifest.json，前一版证据不改写。

## 行为

- XLSX/CSV模板、规范化候选、预览JSON和页面均不包含进价。明确拒绝含“进价”或cost_price列的文件，提示使用新模板，不静默吞掉成本值。
- 解析版本为products-sheet-v2；旧未确认任务需要重传，旧回执按当前商品字段白名单投影，内部成本不再返回。已确认回执保持幂等，不重复创建。
- 原有SKU成本列保留；新增商品只沿用兼容占位0，不能解释为实际进价或利润依据。不更新已有商品成本，也不新增迁移或独立成本管理。
- 买家商品列表/详情DTO原本就没有cost_price，核对源码并增加真实HTTP回归，避免把商家后台模板问题误称为已发生的买家数据泄漏。

## 实际验证

1. `node client/tests/product-import.test.js`：6组行为通过，包括商品预览只显示售价/市场价、旧任务阻止确认、原确认/重试/账号隔离等保护。
2. `python manage.py test goods.test_product_import.ProductImportParserTests --settings=support_ai.test_settings --noinput --verbosity=1`：10项通过，不创建或访问数据库。
3. `& .scratch/product-import/start-test.ps1`及`& .scratch/product-import/run-test.ps1`：专用无端口MySQL8.0.46与应用测试服务，26项全部通过，含旧成本模板拒绝、旧任务DTO不含成本、旧任务提交拒绝、买家列表/详情不返回成本，以及此前的事务/并发/库存用例。500行完整入库约4.069秒，仅为隔离样本。原始日志见mysql-tests.txt。
4. 浏览器通过实际8767临时应用服务上传9列表头的XLSX，3条候选全部通过，价格区域仅有38.50/45.00、98.00/128.00、68.00/88.00；没有进价列。本轮浏览器仅校验预览，不确认写入。截图见[preview.png](preview.png)。
5. Node语法、Django系统检查、无新增迁移检查、模块归属及相关diff空白检查通过。

临时浏览器服务固定使用新建的browser-no-cost.sqlite3，MySQL连接被禁止；数据库回归只使用此前同类独立Docker内部网络和临时tmpfs MySQL，连接守卫仍限制import-db。未查询业务数据库或使用真实账号。收尾停止本轮38600预览进程、ef8e0f8c03053c108d9d9e414303737e87452f9566d1b3844a677468f2747210临时MySQL容器并移除专用网络。

未执行业务库迁移、8000服务重载、提交/推送或部署；首版任务表尚待正式启用。本轮其余MCP/Agent并行改动继续保留，不属于本轮结论。
