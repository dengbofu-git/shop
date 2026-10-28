# 会话单方隐藏本地启用

日期：2026-10-22，Asia/Shanghai。用户在明确询问本地迁移及服务更新后回复“执行”，授权本次本地启用；不包含Git提交、推送、PR更新／合入或远端部署。

## 实际执行

- 核对本地8000服务原进程11868、项目解释器及`manage.py runserver 127.0.0.1:8000 --noreload`参数。迁移计划严格只有`engagement.0002_conversation_visibility`，新增`buyer_hidden`和`merchant_hidden`，不执行其他待迁移项。
- 暂停原服务后，确认Django连接与本机MySQL容器实例一致，完成单事务完整SQL备份；备份结束标记、咨询表建表内容及落盘SHA256校验通过。
- 备份位于本机忽略目录`.scratch/conversation-hide-20261022/local-activation/before-visibility-20261022T100736Z.sql`，988,406字节，SHA256为`9b40792d5359ccf405da341ad48ef864eb78d7d849336a1edc83de91f5f52d40`。未将SQL或消息正文纳入Git，未回退业务数据库。
- 执行定向`python manage.py migrate engagement 0002_conversation_visibility --database default --noinput`成功。迁移记录仅增加这一项；两端新标记均为False，原有2个会话及4条消息的全部原始字段、行数和内容哈希一致，已读位置未变。
- 按原工作目录、解释器和启动参数恢复本地服务，新进程29988，仅监听`127.0.0.1:8000`。启动系统检查无问题；其他模块`ai_storage`、`inventory`、`orders`共4项待迁移不在本次范围内，保持未执行。

## 验证

执行本机忽略目录中的`verify_local.py`，16项只读HTTP检查通过：买家／商家消息页、3份静态资源、匿名认证拒绝、双方身份与已有会话列表／历史，以及新隐藏／恢复路由GET方法拒绝。页面使用新缓存标识，菜单没有额外说明。短期JWT只保存在内存，不保存令牌、账号凭据或消息正文。

浏览器先确认当前输入框无草稿，再刷新原有本地消息页。真实会话和消息正常加载，右键显示删除图标及“删除对话”，不显示“仅对自己隐藏，消息保留”。截图保存在忽略目录`.scratch/conversation-hide-20261022/local-activation/menu-live.png`。检查没有点击真实会话删除操作、发送消息或创建测试业务数据。

HTTP和页面验证后再次运行`activate.py verify`，原有会话／消息字段哈希仍一致，本次目标无待执行迁移。功能行为的隐藏、恢复、新消息和并发验证沿用此前[隔离测试](verification.md)，未在业务库制造测试会话。

本次完成本地备份、迁移、服务恢复及只读验证；没有执行Git交付、远端部署或其他模块迁移。
