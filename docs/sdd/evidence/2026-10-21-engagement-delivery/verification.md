# 咨询与评价交付验证

本次交付分支：codex/engagement-delivery。由原工作区的咨询与评价增量提取，采购页调整及其他worktree的业务修复未混入。工作区原有改动保留。

已正常合并最新origin/main。被测源提交：`d71373c44bc3dc1152bc20e9dce385f03c552eb1`；main提交：`b9fa6c1218b586ec1e708a11487c21ccb59c24a5`。之后仅补充交付文档和证据，运行代码由[源码哈希](manifest.json)绑定；最终交付SHA见PR正文。

版本：core 0.6.1、engagement 0.1.0、orders 0.2.0、goods 0.5.3、supplier 0.3.1、web 0.25.0。合并保留main的CI固定与清理记录；五份冲突均为版本／说明文件，没有历史迁移或业务语义冲突。合并带入CI实现变化，按门禁将core从0.6.0递增至0.6.1。

## 同步后实际验证

Python 3.9.25、Django 3.2.12，使用现有项目运行环境；本机包装脚本仅向隔离分支加载配置环境和工作区临时目录，不复制真实凭据到仓库。SQLite和MySQL均由隔离设置运行。

| 检查 | 实际命令／内容 | 结果 |
| --- | --- | --- |
| SQLite相关回归 | 本机包装脚本run_checks.py sqlite；执行engagement、goods.test_activity、goods.test_images、goods.test_catalog_pagination、goods.test_sales_recommendations、supplier.test_store_pages、users.tests，使用support_ai.test_settings | 101项，96通过、5条件跳过；[日志](sqlite.log) |
| MySQL迁移及并发 | 本机包装脚本run_checks.py mysql；执行engagement，使用engagement.test_mysql_settings的随机test_engagement_*临时库 | 36项全通过，含3项真实行锁并发；[日志](mysql.log) |
| 前端行为 | node --test client/tests/engagement.test.js client/tests/auth-storage.test.js | 5项通过；[日志](frontend.log) |
| 治理 | python -m unittest tools.tests.test_git_policy tools.tests.test_project_identity tools.tests.test_module_versions | 29项通过；[日志](governance.log) |
| 交付规范 | python tools/git_policy.py verify --base origin/main | 71个变化文件、16模块、25个Python/JS语法检查通过；[被测提交日志](policy.log)，后续仅增加文档证据，最终SHA再次检查 |
| Django与迁移一致性 | run_checks.py check：check、makemigrations --check --dry-run | 无系统问题，No changes detected |

实施阶段的MySQL旧订单向前升级检查复用：[结果](../2026-10-21-engagement/mysql-upgrade.log)。已逐字节确认orders/models.py、orders新增迁移、engagement/models.py与engagement新增迁移在本次隔离分支完全相同；历史金额／商品项保留、不补造旧快照的结论没有输入变化。浏览器主流程、三语和手机RTL截图也保留为实施阶段证据，本次页面路由渲染与业务测试已重跑；没有将旧截图声称为同步后的新浏览器测试。

实施阶段报告中记录的三份旧证据命名失败，已随main既有修复正常合入；本次命名空间与模块归属检查均通过。未改写旧报告的历史事实。

## 范围与限制

- 没有引入原工作区尚未提交的采购页调整、或其他worktree的拆单／发货修复；主干已有的清理和CI修复正常保留。
- 所有数据库验证在隔离库；未迁移业务数据库、未批量修改业务记录、未部署、未真实支付或调用模型。
- 旧订单缺购买快照的限制保留；支付可信回调、完整试单／预售流程及高并发容量不属于本次验收。
- 只创建面向main的PR，不合入、不发标签；临时交付worktree在PR合入前保留，不能提前清理。

本次未迁移业务数据库，不部署，不创建版本标签；仅按用户授权提交、推送并创建面向main的PR。
