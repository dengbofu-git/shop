# XLSX／CSV 商品批量导入验证

日期：2026-10-28（Asia/Shanghai）。CAP-CAT-002／FEAT-005；规格 [product-import.md](../../modules/catalog-content/product-import.md) 0.1.0。开发分支 `codex/goods-bulk-import`，起点 `63fa850843771dde21c7bd49ed9bc98019e5d24a`；未提交工作区的本轮文件 SHA256 见 manifest.json。实现版本 goods0.7.0／web0.32.0／core0.8.4；本轮未接入merchant_ai或模型。

## 实际结果

| 验证 | 结果与覆盖 |
| --- | --- |
| 独立MySQL8.0.46应用测试服务 | **23项通过**。实际执行goods0012迁移；认证/商家隔离、逐行校验、XLSX与CSV模板回读、上传边界、预览后冲突、摘要校验、过期、库存账本、停用仓库、原子回滚/可重试、上传幂等、确认幂等及两个并发场景。AC-IMPORT-02～07 |
| 500行最大批次 | 同一商品下500个规格全部写入未上架SKU、500条库存账本和500条日志。最终一轮上传到确认约4.620秒；前一轮约8.997秒，仅为本机隔离样本，不代表生产SLA或负载压测 |
| 控制器VM测试 | 5组行为通过：未确认不写、非法批次阻止、纯文本防HTML解释、分页/错误筛选、新文件失效旧预览、上传重试复用键、请求中关闭保护、账号变化丢弃旧结果、错误DTO拒绝、刷新走认证任务接口。AC-IMPORT-01/08 |
| 原商品预览回归 | merchant-product-preview.test.js通过；只读商品预览及安全文本保持 |
| Django/语法/归属 | manage.py check无问题，makemigrations goods --check --dry-run无变化；Python编译、Node语法检查、模块归属检查和本轮diff --check通过 |

本机最初SQLite定向测试21项执行，19项通过、2项MySQL并发检查按后端跳过；随后扩展到上述23项并在真实隔离MySQL全部执行通过，不能将SQLite跳过项计为已验证并发。

## 浏览器真实应用服务验收

临时服务仅绑定127.0.0.1:8767，Django使用独立 `.scratch/product-import/browser.sqlite3`；MySQL连接函数被显式禁止。商家身份与所有商品均为合成夹具，未使用业务账号。静态资源与新增业务API为本轮实际实现，无上传/导入响应模拟；旧init.js的固定8000地址只在夹具服务中改为当前origin，防止旧页面请求误入业务服务。

- 创建商品页的批量导入按钮打开弹窗，单条创建表单保留。
- 上传错误CSV：价格待定、库存-1在原文件第2行显示错误；确认框与按钮禁用。[错误截图](errors.png)
- 上传有效XLSX：两个商品、三个规格；价格38.50/98.00/68.00、库存120/30/60均显示；未勾选不能确认。[预览截图](preview.png)
- 刷新相同URL后通过服务端恢复同一UUID任务，确认勾选清空，未创建商品。
- 勾选并确认：真实服务返回新增2个SPU、3个SKU，全部未上架；刷新回执仍是committed，确认按钮禁用。[回执截图](success.png)
- 再上传并确认有效CSV：新增1个SPU、1个SKU，50.00元、库存20；点击查看商品列表，共4个规格，价格与库存对应，均下架。[商品列表截图](products.png)
- 下载XLSX模板通过携带认证的fetch下载，文件在本机Downloads；HTTP自动化测试另验证XLSX和CSV模板均可重新解析。浏览器error日志为空。

本轮未验证手机窄屏、500行浏览器渲染负载和多进程生产部署。23项后端测试覆盖真实500行入库；控制器分页使用27条夹具，不宣称500行浏览器压力测试通过。

## 数据库隔离与命令

Docker专用内部网络 `tea-saas-import-check-20261028`；临时MySQL容器 `tea-saas-import-mysql-check-20261028` 无宿主机映射端口、无业务卷，数据仅临时tmpfs。应用测试进程的数据库配置只指向import-db，连接守卫只接受该主机和固定测试库名称；AI数据库后端设为dummy。未读取/查询业务MySQL或PostgreSQL，没有SQL客户端操作或业务库Migration。

实际命令：

```text
python -m pip install openpyxl==3.1.5 defusedxml==0.7.1
python manage.py test goods.test_product_import --settings=support_ai.test_settings --noinput --verbosity=1
& .scratch/product-import/start-test.ps1
& .scratch/product-import/run-test.ps1
node client/tests/product-import.test.js
node client/tests/merchant-product-preview.test.js
python manage.py check --settings=support_ai.test_settings
python manage.py makemigrations goods --check --dry-run --settings=support_ai.test_settings
python -m compileall -q [本轮新增Python文件]
node --check client/static/js/product-import.js
python tools/module_versions.py check
git diff --check -- [本轮路径]
```

最终MySQL原始记录：[mysql-tests.txt](mysql-tests.txt)。临时服务脚本和私有运行文件留在忽略目录 `.scratch/product-import/`；数据库测试进程结束时已销毁测试库。收尾停止本轮临时浏览器服务与MySQL容器并移除专用网络，不删除其他进程/容器/工作树。

`run-test.ps1` 实际运行 `docker run --rm --name tea-saas-import-app-check-20261028 --network tea-saas-import-check-20261028 --read-only --tmpfs /tmp:rw,size=128m -e PYTHONPATH=/deps:/app/.scratch/product-import -e PYTHONDONTWRITEBYTECODE=1 -e LOG_TO_FILE=false -v ${PROJECT_ROOT}:/app:ro -v ${PYTHON_ENV_ROOT}/Lib/site-packages/openpyxl:/deps/openpyxl:ro -v ${PYTHON_ENV_ROOT}/Lib/site-packages/et_xmlfile:/deps/et_xmlfile:ro -v ${PYTHON_ENV_ROOT}/Lib/site-packages/defusedxml:/deps/defusedxml:ro -w /app tea_saas-knowledge-worker-knowledge-worker python manage.py test goods.test_product_import --settings=mysql_test_settings --noinput --verbosity=2`。设置文件强制隔离连接边界；执行脚本与设置的SHA256一并记录于manifest，未将真实凭据写入证据。

## 交付与启用边界

goods0012仅在上述独立测试服务执行，**未在业务库执行**；未重启8000、未提交/推送/PR或部署。正式服务启用需要单独授权的受控备份、迁移新增任务表与服务重载。否则业务导入接口可能因旧服务路由或缺表不可用，不能将隔离页面截图当作正式启用证据。

实施过程中工作区出现其他任务的MCP与Agent文档/代码修改，本轮保留且不纳入导入功能结论；共享版本清单保留其他新增模块登记。本报告仅覆盖清单中的本轮商品导入文件，不证明其他未提交任务已验收。
