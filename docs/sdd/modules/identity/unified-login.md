# 统一登录与平台权限隔离

日期：2026-10-18（Asia/Shanghai）。本次由用户明确要求取消登录角色选择，按账号权限分流；承接已确认的 merchant001 越权缺陷。涉及 CAP-IAM-001、CAP-IAM-003、CAP-PLAT-001、CAP-PLAT-002、CAP-AI-004；为现有系统的定向增量，实施并通过限定回归，不宣称全站权限梳理完成或已发布。

## 需求与规则

- REQ-LOGIN-001：`login.html` 只显示一个账号密码表单及登录按钮，保留中英阿语言切换和注册；2026-10-19 按用户要求移除已废弃的邮箱找回密码入口。移除角色选择和没有持久化实现的“记住密码”复选框，交由浏览器标准 autocomplete 处理凭据。
- RULE-LOGIN-001：校验密码和账号启用状态后，服务端读取数据库中启用的角色及权限，返回允许的工作台；不使用客户端选择的角色、用户名约定或缓存中的权限决定平台访问。
- RULE-LOGIN-002：平台角色集合为 `super_admin`、`admin`、`customer_service`、`finance`。有其中一个有效角色且有有效 `data_view` 时进入 `/admin_panel.html` 交易总览；否则有 `user_manage` 时进入 `/admin_users.html` 账号管理；否则有 `system_config` 时进入 `/admin_agents.html`。具有平台角色却三项入口权限均无时，返回业务码 `10006`，不返回 Token，不误导进入买家工作台。多角色账号按上述平台规则优先。
- RULE-LOGIN-003：无有效平台角色时，`user_type=merchant` 或有效 `supplier` 角色进入 `/merchant_dashboard.html`；其他 customer 账号进入 `/buyer_dashboard.html`。停用角色不参与判断，不能授予平台权限；账号本身仍为 customer 时可按客户身份进入买家页。
- RULE-LOGIN-004：平台交易总览接口要求有效平台角色与 `data_view`；平台用户管理四种操作均要求有效平台角色与 `user_manage`；所有 Agent 设置、模型、检索状态、监控及链路接口要求有效平台角色与 `system_config`。账号停用或权限撤销即时影响后续请求，已有 JWT 不绕过检查；仅 `goods_manage` 或错误授予供应商 `user_manage/system_config` 均不足以访问平台。
- RULE-LOGIN-005：运营页面加载后，先查询当前会话权限再初始化功能；无权限者转到自己的工作台，未登录者转登录页。页面保护不替代服务端接口鉴权。
- RULE-LOGIN-006：旧 `/terminal_login.html` 重定向统一入口，不保留另一套登录逻辑。旧调用者的 `expected_user_type` 检查继续兼容，但新表单不发送此字段。

## 接口与实现

`POST /v1/users/login` 保留原有字段及业务码。成功新增 `roles: string[]`、`permissions: string[]`、`redirect_url: string`。地址只取五个固定站内页面，前端也校验白名单；错误响应不存储登录状态。原有错误码：用户名空10001、密码空10002、密码错误10003、账号停用10004、旧客户端类型不符10005；新增工作台无权限10006。业务错误沿用 HTTP 200，未重构全站错误协议。

`GET /v1/users/session` 使用 Authorization JWT，返回 `code` 与上述三个权限字段；不返回密码、Token或联系方式。未认证HTTP401，账号停用HTTP403，非GET HTTP405；响应禁止缓存。每次实时读取授权，无数据写入。有效账号没有工作台时 `redirect_url=null`，页面返回登录。

规则集中于 `users/access.py`，平台API使用 `platform_permission_required`；前端统一登录为 `login-portal.js`，运营入口守卫为 `platform-access.js`。模块版本：core0.1.7、users0.2.0、admin_panel0.3.1、web0.7.2；support_ai0.10.1仅更新运营回归测试的平台角色fixture，Agent执行逻辑不变。若成功响应缺少redirect_url，客户端明确提示登录后端版本未更新，不保存Token或降级按客户端身份猜测工作台。

## 数据与兼容边界

2026-10-18后续增量：认证身份只使用当前标签页sessionStorage，不再向localStorage写入或从其回填Token、用户名、店铺及账号类型。刷新和同源iframe共享本标签页会话；空的新标签页需要登录，其他标签页登录／退出不更换当前身份。保留已有sessionStorage，因此更新后应刷新已打开页面，已因旧逻辑混入其他账号的标签页需重新登录。详见[商家预览修复](../catalog-content/merchant-preview.md)。

无新增／修改 Migration，不改数据库账号或授权，不重新执行 `seed_rbac`／`create_super_admin`。现有超级管理员的显式权限继续有效。平台账号持有有效 `data_view` 时可进入交易总览；账号管理和 Agent 管理仍各自要求 `user_manage` 和 `system_config`，不自动扩大岗位授权。不按用户名或店铺名猜测岗位。

Q-009 仅解决统一登录及平台API切片；库存、交易、商家及其他接口的对象范围和停用策略仍待逐项核查。Django `/admin/` 使用独立认证体系，本次不变更。

## 验收场景

| 场景 | 预期 |
| --- | --- |
| 同一表单登录买家／商家／超级管理员 | 分别进入买家／商家／交易总览页 |
| 客户类型且有supplier角色 | 进入商家页；保留商家API原有角色兼容 |
| 平台账号仅有system_config | 进入Agent页，账号管理403 |
| 平台角色没有可用入口权限 | 10006，无Token |
| 修改客户端角色或跳转地址 | 不影响服务端分流 |
| 供应商访问账号CRUD或Agent所有入口 | 403，即使误配单项平台权限仍拒绝 |
| 停用账号／角色／权限或撤销映射，继续使用旧JWT | 对应平台API拒绝 |
| 未登录直接打开运营页／旧终端登录地址 | 回到统一登录页 |
| 中英阿语言切换 | 单一表单保留，阿语RTL |

验证记录见 [本次证据](../../evidence/2026-10-18-unified-login/verification.md)。没有执行部署、推送或真实业务写操作。

2026-10-18 管理端首页调整：现行分流与统计口径见[平台交易总览](../platform/trading-overview.md)。上述统一登录证据为当时版本记录，本次导航与统计验证单独执行。

## 2026-10-19 废弃认证接口移除

用户要求删除短信、邮箱、微博等废弃认证入口。本次删除以下路由及其处理实现，旧请求按未匹配路由返回 HTTP 404，不保留发送验证码、绑定账号或重置密码的兼容处理：

- `/v1/users/sms/code`
- `/v1/users/activation`
- `/v1/users/password/sms`、`/v1/users/password/verification`、`/v1/users/password/new`
- `/v1/users/weibo/authorization`、`/v1/users/weibo/users`、`/v1/users/weibo/users/binduser`

删除 `active.html`、`findPass.html`、`callback.html` 页面与路由、对应脚本／样式和认证邮件模板；移除容联云 SDK 依赖及 SMTP、短信、微博启动配置。注册页 `register_sms.html` 只是沿用旧文件名，当前为普通账号密码注册，不发送或校验短信。

继续保留 `/v1/users/register`、`/v1/users/login`、`/v1/users/session` 与登录后的本人密码修改接口；账号资料中的邮箱、手机号以及历史 `WeiboProfile` 模型／数据表均保留。不新增 Migration，不清理历史数据，不修改部署环境的凭据文件。当前没有自助找回密码入口。

本次只执行静态语法、模块归属与 Django 配置检查，不运行或新增测试；既有短信日志测试及旧页面检查引用随废弃功能移除。此前验收证据仅代表此前版本，不作为本次业务验收结果。
