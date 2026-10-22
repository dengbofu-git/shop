# 多客户／多商家会话与数据库持久化验证

日期：2026-10-22。实现模块 engagement 0.1.2、web 0.27.2。本轮代码未提交、推送或部署；当前分支同时存在其他任务改动，保留原现场。本轮没有新增Migration或向业务库创建测试消息。

## 规则与实现

- 保持数据库 `Conversation(buyer, merchant)` 唯一约束，`Message` 外键关联会话，消息正文、服务端关联卡片、时间、幂等标识、双方已读位置均在数据库持久化。
- 两买家、两商家建立三个配对：买家一联系商家一／二，买家二联系商家一。同配对复用会话，不同配对分别保留消息及未读。商家分别回复已有客户。
- 历史接口增加会话编号及公开店铺名／脱敏买家名，页面选择和首条发送后保存当前会话URL，刷新从接口恢复；列表与标题显示会话编号以区分相同脱敏名。
- 快速切换丢弃旧历史和旧发送错误，列表丢弃过期响应，发送中状态独立于选择；加载历史期间禁止发送，读取失败隐藏发送区并可刷新重试。sessionStorage只保存未发送草稿和幂等重试标识。

## 本轮命令及结果

`python`为本机项目Python 3.9解释器。

1. `python manage.py test engagement.test_conversations engagement.tests --settings=support_ai.test_settings --noinput`
   - SQLite隔离测试：40项，39通过、1项MySQL专用重连用例跳过；既有会话、评价、权限及上下文回归通过。
2. `python manage.py test engagement.test_conversations engagement.test_concurrency.EngagementConcurrencyTests --settings=engagement.test_mysql_settings --noinput`
   - 首次受限环境因WinError10013无法访问本机MySQL；使用工具隔离测试连接授权后，同一命令9项全部通过。
   - 测试配置生成随机 `test_engagement_*` 测试库，NAME与TEST.NAME均指向隔离库，运行后Django销毁该测试库。业务库无消息写入或迁移。
   - `TransactionTestCase`通过HTTP提交消息后确认autocommit，主动关闭数据库连接，再以新连接ORM查询及新HTTP客户端读取同一会话／消息，结果一致。
   - 两买家／两商家列表、分别回复、跨配对读取／发送／已读拒绝、双方独立未读，以及并发首条消息幂等通过。并发评价原有两项同组回归通过。
3. `node --test client/tests/engagement.test.js client/tests/engagement-messages.test.js`
   - 14项全部通过。
   - 运行真实控制器与受控异步HTTP响应：验证多会话编号、URL刷新恢复、延迟历史、旧会话发送失败／成功、草稿保留、列表过期响应、历史读取失败重试与空会话状态。
   - 保留同源当前标签页令牌、文本安全渲染、三语词条回归。
   - 单独接收游标不随本地发送跳跃，交错消息按服务端ID顺序插入；批次尚未拉完时，已读不越过已获取的历史位置。
4. `python tools/module_versions.py check`：16模块归属有效。
5. `git diff --check`：通过；没有暂存、提交、推送、创建PR或更新运行服务。
6. `python manage.py makemigrations engagement --check --dry-run --settings=support_ai.test_settings`：无模型变更；买家与商家模板实际渲染及主要ID唯一性检查通过。
7. 浏览器打开现有商家工作台的“买家咨询”：中文标题、按客户归档说明、空会话提示及单页隐藏分页实际可见。只检查当前空列表，没有发送真实消息；多对象消息内容及切换由隔离HTTP与控制器测试覆盖。截图留本机忽略目录 `.scratch/conversations-20261022/merchant-inbox.png`。

SQLite回归不能证明MySQL行锁；重连与并发结果来自上面的实际隔离MySQL测试。没有使用真实账号向客户／商家发送演示消息，没有新增WebSocket、主动群发或客户目录。
