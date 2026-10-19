# 登录页茶文化视觉验证

日期：2026-10-19，Asia/Shanghai。模块 `web 0.16.1`，本地分支 `codex/core-tea-saas-rename`。未暂存、提交、推送或发布。

## 结果

主题图与透明 Logo 已通过内置 image_gen 生成，复制到仓库静态资源目录，并接入登录页、favicon 与触屏图标。选用的生成提示词、尺寸和 SHA-256 见[素材记录](assets.json)；Logo alpha 范围 0—255，角落像素完全透明。首个 Logo 草案未选用，没有接入代码。

标题、图片替代文字、主文案、欢迎语、表单标签及底部说明均更新，移除原口号和赛事说明；品牌名保留为 `tea_saas`。静态资源引用附本轮版本标识，公共工作台样式保持原样。布局与有效规则见[规格](../../modules/platform/login-visual-identity.md)。

## 实际验证

- `node client/tests/unified-login.test.js`：通过。覆盖服务端目标地址白名单、权限跳转、失败恢复与存储边界。
- `node client/tests/tea-saas-brand.test.js`：通过。覆盖中英阿品牌契约。
- `node --check client/static/js/login-portal.js`：通过。
- `python client/tests/tea-saas-contract.py`：25 个页面壳及既有契约通过。退役路径返回的 404 为测试预期。
- `python tools/module_versions.py check`：15 个模块归属通过。
- `python -m unittest tools.tests.test_project_identity -v`：2 项通过。
- `git diff --check`：通过。

上述 Python 使用现有本机业务解释器。页面契约使用隔离测试设置；未运行整站业务回归、数据库迁移或模型评测。

浏览器实际刷新 `http://127.0.0.1:8000/login.html` 后验证：

- 1440 × 900 桌面双栏，主题图与 Logo 均加载成功，无损坏图片、无横向溢出，见[桌面截图](desktop.png)。
- 中、英、阿三语切换同步改变浏览器 title、图片替代文字与正文；阿拉伯语按 RTL 显示。英文标题为 `tea_saas · Tea Trade Workspace`，阿拉伯语为 `tea_saas · مساحة تجارة الشاي`。
- 390 × 844 手机尺寸，主题横幅与表单纵向排列，采用自然纵向滚动；无横向溢出，见[手机截图](mobile.png)。

浏览器临时尺寸在验证后恢复默认，语言恢复中文。没有输入真实凭据或执行登录；本轮只验证界面与既有登录逻辑的隔离测试，不宣称真实业务库登录已通过。当前本机服务状态限制继续参见[命名轮次的运行记录](../2026-10-19-project-rename/verification.md)。
