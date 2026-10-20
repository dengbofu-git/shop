# 店铺页面首版验证记录

日期：2026-10-20（Asia/Shanghai）。类型：verification。能力：CAP-MER-005，来源 FEAT-036；规格为 [店铺页面首版](../../modules/merchant-operations/store-pages.md)。执行：Codex；未进行独立人工评审或生产验收。

## 版本与现场

- 分支 `codex/supplier-store-pages`，基线 HEAD `f382e8e366279a7e2bbc66747ed84f0c7f44cbe6`。代码尚未提交，不能仅凭此 SHA 复现本次实现；受影响实现文件 SHA256、模块版本和环境见 [manifest.json](manifest.json)。
- 模块：supplier 0.3.0、goods 0.5.0、web 0.23.0、core 0.5.0。保留开始前已有的订单、轮播、卡片、分页与其他文档修改；没有暂存、提交、推送、PR、标签或部署。
- 本次新增 `supplier.0002_storepage`，只在隔离 SQLite／MySQL 测试库迁移验证，未迁移或写入业务数据库。另建 `.scratch/store-pages/preview.sqlite3` 和独立素材目录，浏览器演示只使用两家合成店铺与合成商品，不调用模型。

## 自动检查

| 实际命令／环境 | 结果与覆盖 |
| --- | --- |
| `python manage.py test supplier.test_store_pages goods --settings=support_ai.test_settings --noinput --verbosity=1`，TMPDIR 指向本任务可写目录 | 最终53项，51通过，2项MySQL并发专用用例跳过；见 [SQLite日志](sqlite-final.log)。覆盖发布、归属、商品、上传、图片与分页回归 |
| `python .scratch/store-pages/mysql_tests.py`，默认仅 supplier.test_store_pages | 最终21项全部通过；完整迁移在新建 `test_store_pages_a0b93263a601` 执行，结束后销毁该测试库。包括店铺一对一／JSON持久化、乐观并发版本、推荐聚合SQL、权限、草稿与公开投影；见 [MySQL日志](mysql-store-final.log) |
| `node client/tests/storefront.test.js` | 通过；导航归属、纯文本渲染、未发布链接、预览不提供购买操作 |
| `node client/tests/buyer-products-pagination.test.js` | 通过；103项跨11页、分类、完整脚本渲染和语言保留 |
| `node client/tests/buyer-catalog-preview.test.js` | 通过；首页103项分页、边界、空态与失败重试 |
| `node client/tests/merchant-product-preview.test.js` | 通过；原商家商品预览维持只读，不跳入买家导航 |
| `node --check`：storefront.js、store-page.js、merchant-store.js、buyer-products.js、buyer-workbench.js、supplier-workbench.js | 通过；不以语法检查替代业务验收 |
| 提取 product_details.html 内联脚本后 `node --check` | 通过；浏览器联调曾发现新增入口位置打断原 if/else，已修复并重新点击验收 |
| `python manage.py check --settings=support_ai.test_settings` | 无问题 |
| `python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings` | No changes detected；新增迁移与模型一致 |
| `python tools/module_versions.py check`、`git diff --check` | 通过；15模块路径有归属；Git CRLF提示不是失败 |

初次 SQLite 执行因沙箱系统临时目录不可写失败；调整本任务 TMPDIR 后重跑通过，没有修改业务实现来绕过测试。

扩大 MySQL 到 `supplier.test_store_pages goods` 的回归尝试运行43项，出现2个既有测试类 setUpClass 失败：`goods.test_catalog_pagination` 使用超出分类 name 长度的 `Pagination fixture`，`goods.test_sales_recommendations` 使用超出账号 username 长度的 `sales-shop-<n>`。MySQL报1406，发生于夹具创建、尚未进入业务断言。两份测试文件本次未修改，未更改字段长度或关闭严格模式。见 [扩大回归日志](mysql-expanded.log)。不能宣称整个 goods 在 MySQL 全部通过；本次受影响的店铺、平台索引、详情及推荐聚合SQL另由最终21项MySQL定向用例通过验证。

## 浏览器实际操作

使用内置浏览器访问本机 `127.0.0.1:8766` 独立测试服务，SQLite与媒体均在 `.scratch/store-pages/`。演示入口 `/__preview__` 仅为本机测试提供合成买家／商家会话，不属于正式源码路由、不会交付到业务服务。该服务的 init.js 仅在隔离演示中指向同源地址，防止现有固定8000的前端配置跨入业务服务。

- AC-STORE-001：买家平台首页的10个卡片同时包含“山间茶事”和“青岚茶园”；分别存在正确店铺链接。点击青岚商品的“店铺详情”进入 merchant_id=4，显示该店3件商品。
- AC-STORE-002：接口定向测试覆盖匿名、买家、停用账号、supplier角色、跨店参数／商品／素材归属；公开快照不含账号、联系方式和草稿。此权限边界由测试验证，不把界面隐藏当授权。
- AC-STORE-003：商家从侧栏打开嵌入管理页；修改欢迎语并保存草稿，公开页仍显示旧欢迎语；点击发布后刷新公开页显示“山间好茶，欢迎来坐坐”。下线不连带下架的规则由API测试验证。
- AC-STORE-004：买家通过平台商品名进入商品详情，详情显示所属店铺，再进入merchant_id=3；本店12件商品，第2页实际2件；店内搜索不存在的词返回0件和空态。排序／分类／售罄过滤／推荐顺序由API测试覆盖。
- AC-STORE-005：实际打开预览弹窗，商品购买按钮禁用。店铺页与管理页分别在390px宽度验收，页面clientWidth与scrollWidth均为375px（包含浏览器滚动条的视口扣除），无水平溢出。店铺顶部搜索原先溢出，已作仅本页面的换行修正并复验。编辑版本冲突由API测试覆盖。
- AC-STORE-006：有效图片重编码、错误图片／跨店素材被拒绝、内容纯文本渲染由后端与Node测试覆盖；未用浏览器重复执行图片选择器上传，也未执行真实交易或付款。

截图均为合成演示数据：[管理面板](manager.png)、[店铺主页](storefront.png)、[平台首页](platform.png)、[店铺窄屏](storefront-mobile.png)、[管理窄屏](manager-mobile.png)。

## 首次交付边界与后续本地启用

首次开发交付时实现与隔离验证已完成，业务库迁移、8000业务服务重载、真实商家发布验收尚未执行；没有发布现有商家资料或改动其商品。店铺编辑与主页内容首版为中文，沿用原工作台导航语言能力，不宣称全页面三语验收。

启用必须先按仓库规则获得业务数据库迁移／本地服务加载授权，核对目标与备份后应用 `supplier.0002_storepage`，再让服务加载新代码。goods 商品投影也会查询新增店铺表，不能在未建表时直接重载业务服务。新增迁移未回填店铺；启用后由商家自行保存并发布，未发布店铺的商品仍在平台展示，但店铺入口显示筹备中。

后续用户已明确授权业务库迁移与8000服务重启，现已完成；备份、单一迁移和13项实际HTTP检查见 [本地启用记录](local-activation.md)。真实商家内容仍由商家自行发布，本次未代发布。
