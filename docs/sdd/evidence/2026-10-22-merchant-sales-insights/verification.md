# 商家销售洞察验证记录

日期：2026-10-22。规格：[商家首页真实销售洞察](../../modules/merchant-operations/sales-insights.md)。本轮验证针对本地增量，尚未绑定交付提交 SHA。

## 后端与前端

- `python manage.py test supplier.test_insights supplier.test_workbench supplier.test_analytics --settings=support_ai.test_settings --noinput` 对应 DiscoverRunner：隔离内存 SQLite，30项通过，包含新增销售洞察12项、待办10项、既有销售统计8项。
- 相同标签使用 `engagement.test_mysql_settings`：随机独立 MySQL 测试库，30项通过，框架创建与销毁临时库，不在业务库试跑迁移。
- 覆盖已付资格、预售／试单、跨商家隔离、历史成交价格、商家快照与商品转移、同名商品区分、规格汇总、数量／金额不同排序、TOP5限制、价格边界及购买件数权重、异常样本披露、空集、365天起止边界、跨年与自然月、访问权限及缓存头。
- 初次 SQLite 验证中2项即时创建样本的排名测试未通过；普通测试样本改为明确处于窗口内部，避免创建时间与排他结束时刻相同。专门的起止边界测试保留，之后 SQLite／MySQL 验证均通过。
- `node --test client/tests/merchant-insights.test.js client/tests/merchant-overview.test.js client/tests/merchant-workbench-feed.test.js`：17项通过，其中新增洞察8项。覆盖失败清除与恢复、真实零值、迟到响应、切换账号、无认证、离页取消、非法响应、商品名纯文本、条形与指标一致、价格区间和三语金额／月份。
- Django `check` 无问题，`makemigrations --check --dry-run` 无变化，`merchant_dashboard.html` 模板编译成功；工作台脚本语法检查通过。

## 当前数据核对

以只读 MySQL 会话遍历6个具有商家入口的有效账号，独立汇总本店符合条件的明细，并与本地 HTTP `/v1/supplier/insights` 比对：总金额、购买件数、已付订单去重数、数量／金额榜单、价格区间件数、月份金额及笔数全部一致。伪造查询参数 `merchant_id` 不改变当前账号范围，未知来源字段均为 null。核对过程中未生成订单、商品、消息或其他业务数据。

本地浏览器复用已有模拟商家会话：8笔已付订单、13件商品、641.00元与数据库一致；热销榜商品名／件数正确，价格分布13件均落在80元以下；月表当前月8笔／641.00元、其余月份为真实零值，金额榜与数量榜顺序分别正确。行业页仅显示未接入说明，Home／End键切换页签正常。中文／英文／阿拉伯文切换、手动刷新及窄屏条形布局通过，浏览器未捕获页面错误。后端已重新加载新接口，保留本地预览。

`python tools/module_versions.py check` 通过；本轮共享文件 `git diff --check` 通过。未暂存文件，保留此前和同期的其他工作区改动。

运行使用既有 Python 3.9／Django 3.2.12、Node 和 MySQL 环境。原始只读结果、过程日志与本地预览截图保存在忽略目录，不向共享文档复制账号凭据、收货信息或原始业务明细。

未执行全站回归、外部行业数据接入、生产部署、Git 提交、推送或 PR。未新增迁移，既有 ai_storage 待迁移项没有执行。本轮仅更新首页指定区域，其他看板历史推算指标仍保持原实现，不能视为已经完成全站真实数据治理。

## 价格分布排版增量（web 0.28.2）

本轮只修改价格分布前端：卡片显示人民币CNY，区间行显示每件单位，使用自然语言端点标签；数值区间以LTR隔离，避免RTL逆转端点顺序。区间与占比／件数同排，比例条统一占满下一行，不改变后端金额、分桶或件数。

- `node --test client/tests/merchant-insights.test.js`：9项通过，覆盖三语单位、端点含义、零值及原比例值。首次新增测试假定Arabic一定使用阿拉伯数字，当前运行时实际使用拉丁数字；改为按当前Intl格式校验后通过。
- `node --check client/static/js/merchant-insights.js`、`python tools/module_versions.py check`、`git -c core.safecrlf=false diff --check`均通过。
- Python3.9以`support_ai.test_settings`实际渲染商家工作台模板及查找CSS／JS资源，通过；未访问业务数据库。
- 浏览器以实际模板销售洞察区域、主题样式和控制器配合本地示例API验证。默认桌面和390px窄屏均显示人民币／每件单位；四行比例条同宽、左边界一致，无区间行横向溢出；中文、英文及阿拉伯文RTL均通过。示例API仅在临时预览中替代fetch，不使用真实凭据及业务接口。
- 预览截图`.scratch/price-layout-20261022/desktop.png`为示例数据。验证后恢复默认视口，关闭临时标签页及本地服务。完整工作台认证／刷新流程未重测；无后端变化，不重复数据库测试。
- 未提交、推送或部署。
