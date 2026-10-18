# 管理端交易总览与嵌入导航验证

日期：2026-10-18。工作区实现，未提交、推送或部署。需求见[平台交易总览](../../modules/platform/trading-overview.md)。

## 自动验证

- `E:/miniconda/envs/dadashop/python.exe manage.py test admin_panel.test_overview users.tests --settings=support_ai.test_settings --noinput`：22项通过，Django系统检查无问题。所有测试使用自动销毁的内存SQLite，合成账号，购物车mock，不连接业务库。
- `node client/tests/admin-shell.test.js`：通过。覆盖账号／Agent的iframe内容切换、返回总览卸载iframe、未知及无权限hash回退、缺少总览权限时选择可访问功能、统计失败清空旧值并可重试。
- `node client/tests/unified-login.test.js`：通过。覆盖登录地址白名单、错误恢复、单项及任一入口权限守卫。
- Python AST、`node --check client/static/js/admin-overview.js`、`python tools/module_versions.py check`、`git diff --check`：通过。上述静态检查不冒充业务或浏览器验收。

## 当前本地服务

沿用原有配置重载 `127.0.0.1:8000` 的无自动重载预览进程，不执行Migration或账号、权限、订单写操作。

- 交易总览阶段：只读事务获取既有有效平台账号用于本机HTTP只读请求，不输出令牌。会话和交易统计均HTTP200，返回30天序列；实际MySQL聚合成功。
- 嵌入调整后：不携带账号或凭据的GET检查确认 `admin_users.html`、`admin_agents.html` 均302至 `/admin_panel.html#users`、`#agents`；各自 `?embedded=1` 返回200且不包含重复导航或退出按钮。

## 浏览器范围

交易总览阶段曾在8001独立内存库，以合成订单和账号验证桌面指标、近30天趋势、每日明细、刷新及账号页面导航；未写业务数据。

后续改为统一外壳与iframe，初次登录验收因缺少明确授权被自动审批拦截。用户随后明确回复“允许登录验收”，已使用8001内存SQLite的合成账号完成浏览器检查：

- 登录后进入 `admin_panel.html#overview`，点击账号管理后根页面仍为 `admin_panel.html#users`，iframe加载 `admin_users.html?embedded=1`，账号内容可见且只有外壳一份导航。
- Agent 管理在 `#agents` 内嵌加载，知识库文件区域可见，提交按钮禁用，内页没有重复导航。
- 发现并修复iframe额外历史导致返回时导航／内容错位：子页面使用location.replace，父页面hash负责导航历史。重新实测“总览→账号→Agent→返回→返回”，依次恢复账号和总览，高亮与内容一致。
- 控制台错误为空。模型列表和重排序状态仅用测试替身，不进行真实模型或重排序服务调用；未点击保存、创建或删除。
- 最终截图：[账号管理嵌入](embedded-users.png)、[Agent管理嵌入](embedded-agents.png)。截图仅含合成数据。
- 修复后重新运行 `node client/tests/admin-shell.test.js`、`node client/tests/unified-login.test.js`、JS语法、模块归属及Diff检查。此前22项后端测试覆盖的Python实现未修改，复用其通过结果。
