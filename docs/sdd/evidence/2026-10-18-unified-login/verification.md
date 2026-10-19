# 统一登录验证记录

日期：2026-10-18；本地分支 `codex/users-unified-login`。规则见[统一登录与平台权限隔离](../../modules/identity/unified-login.md)。未提交、推送或部署；本记录对应工作区实现，不宣称已发布。

## 自动验证

`E:/miniconda/envs/tea_saas/python.exe manage.py test users.tests support_ai.test_telemetry --settings=support_ai.test_settings --noinput`：27项通过。使用自动销毁的内存SQLite和合成账号，购物车Redis访问mock，不连接业务库、不调用外部模型。覆盖统一入口与旧地址、四种工作台地址、伪造客户端角色、平台无权限、停用角色／权限／账号、权限撤销后的旧JWT、供应商对账号CRUD及全部Agent接口的越权拒绝、合法运营账号CRUD及原有Agent运营配置／审计／监控回归。日志中的 `Agent telemetry persistence failed: RuntimeError` 是已有异常路径测试的预期日志，最终结果为OK。

`node client/tests/unified-login.test.js`：通过。运行实际登录和运营守卫脚本，验证四个固定地址成功跳转、外部／未知地址拒绝、不保存失败登录Token、业务和网络失败后按钮恢复、平台角色与功能权限共同控制页面初始化。此项为Node行为测试，不冒充浏览器全链路登录。

`python tools/module_versions.py check`：15模块归属检查通过；`git diff --check`通过。Python／JavaScript语法、Django系统检查及文档链接另外核对。

## 当前数据库只读复核

使用Django业务配置连接当前MySQL，先执行 `START TRANSACTION READ ONLY`，结束后rollback；不执行Migration、种子或账号更新。不读取／显示密码，不修改真实账号。鉴权复核通过服务器内部RequestFactory调用真实URL对应视图，不是通过账号密码在浏览器登录。

- merchant001：启用的merchant，角色只有supplier；权限goods_manage、inventory_manage、order_manage；服务端返回 `/merchant_dashboard.html`。
- `GET /v1/users/session`：HTTP200。
- `GET/POST/PUT/DELETE /v1/admin-panel/users`：全部HTTP403，写方法在鉴权层拒绝，未触达业务操作。
- `GET /v1/admin-panel/agent/settings`：HTTP403。

## 浏览器检查

访问当前本地服务 `http://127.0.0.1:8000/login.html`，只有账号、密码和登录按钮，没有角色选择；中文、英文和阿语切换正常。未登录访问账号管理页面自动返回统一登录；旧终端登录地址同样回到统一登录。未用真实用户密码执行浏览器登录，没有修改浏览器持久凭据。

页面截图：[login.png](login.png)。未执行真实支付、外部模型请求、全站对象权限验收或移动设备全链路验收；其他业务API的对象范围仍由Q-009追踪。

## 后续问题与运行中服务复核

用户反馈admin登录显示“没有可访问的工作台”。数据库只读核查确认admin为启用的super_admin，拥有user_manage和system_config，账号配置无误；实际8000服务的 `/v1/users/session` 却返回404。原因是旧预览进程以 `--noreload` 启动，仍加载修改前的Python模块，而HTML和JS已读取新文件。此前内部RequestFactory验证不能证明运行中的HTTP服务已更新；此前浏览器对旧终端地址的观察亦不能作为当前后端路由已加载的证据。

已核对监听端口进程身份后，沿用原预览脚本及配置重启本地8000服务，不修改任何账号或权限。通过真实HTTP使用配置中已有的管理员初始凭据单次登录成功：HTTP200、code200、redirect_url=/admin_panel.html；不记录密码或Token。真实HTTP复核admin会话和账号列表均200，merchant001会话返回商家地址，账号管理仍403。

web0.7.2新增旧服务响应提示及回归：成功响应缺少redirect_url时提示重启后端，不误报权限不足，不保存Token。Node行为测试再次通过，模块归属与Diff检查通过。服务沿用原有无自动重载启动方式；后续Python变更仍需重启，不能仅刷新浏览器。
