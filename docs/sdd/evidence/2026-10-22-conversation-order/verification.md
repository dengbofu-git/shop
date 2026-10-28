# 会话拖动排序验证

日期：2026-10-22。关联CAP-MER-006／FEAT-037；engagement 0.2.1、web 0.30.1。继续现有本地开发分支，保留其他任务现场；没有提交、推送、PR更新、远端部署或数据库迁移。

## 行为与范围

- 鼠标左键按住会话卡片拖动，经过其他卡片时调整位置，松开保存；提供抓手光标、拖动卡片虚线／透明度、其他卡片让位动画及列表边缘滚动。减少动态效果偏好下跳过位移动画。
- Esc、列表外释放取消，拖到输入框等位置时阻止默认文本插入。拖动过程不替换列表卡片，不切换当前聊天，松开后的意外click不会打开另一会话；Alt+上下方向键也可调整。
- 手动顺序按当前账号、买家／商家端分别保存在当前浏览器，刷新后恢复，不跨浏览器或设备同步。最多200个会话；超限或存储不可用时提示。既有手动顺序保持，未排序的新会话置后；右键隐藏功能保留。
- GET conversations可携带order，先按本人可见范围排序再分页，其他会话沿用最近消息顺序。只改变当前请求的排序；非法、重复、超长参数返回400，外部／隐藏ID不产生越权结果；无新增模型字段或迁移。

## 实际验证

| 命令或检查 | 结果 |
| --- | --- |
| `node --test client/tests/engagement.test.js client/tests/engagement-messages.test.js` | 34项通过；包括拖动提交／取消、轮询稳定、误点击抑制、列表外丢弃草稿保护、刷新、账号／角色隔离、后续页锚定及存储失败 |
| `python manage.py test engagement.tests engagement.test_conversations engagement.test_visibility engagement.test_ordering engagement.test_visibility_migration engagement.test_concurrency supplier.test_workbench --settings=support_ai.test_settings --noinput` | 65项中60项通过，5项MySQL专项跳过，使用内存隔离库 |
| 上述集合改用`--settings=engagement.test_mysql_settings` | 65项全部通过；随机隔离MySQL库创建／销毁，涵盖排序前分页及参与者可见范围 |
| `python manage.py check --settings=support_ai.test_settings`及`makemigrations engagement --check --dry-run`同设置 | 系统检查通过，engagement无缺失迁移 |
| 隔离设置模板渲染、staticfiles资源定位、模块归属及本次文件空白／冲突检查 | 通过，缓存标识更新为20261022-conversation-order |

独立示例预览使用实际模板／样式／控制器与模拟API：浏览器执行Alt+上移后云间茶铺从第二行变为第一行，当前聊天仍为云间茶铺；刷新仍保持手动顺序，卡片DOM属性draggable及grab光标生效。截图`.scratch/conversation-order-20261022/order.png`为示例排序结果。浏览器工具没有可用的按住鼠标拖动接口，因此未声称实际执行原生鼠标拖动；拖动、取消、列表外释放通过实际控制器事件测试覆盖。临时标签页和示例服务已关闭。

## 本地启用

沿用用户已授权的本地服务更新范围，核对旧8000服务29988的解释器及启动参数后，按原工作目录与`manage.py runserver 127.0.0.1:8000 --noreload`恢复服务，新进程41400，仅监听本机。未执行数据库迁移，也未应用其他模块待迁移项。

`verify_local.py`对实际本地买家／商家页面、静态资源、匿名认证、双方身份、已有消息读取、正反手动顺序及新隐藏路由方法限制进行了18项只读检查，全部通过。令牌仅在内存；没有发送或隐藏真实消息、修改真实账号排序偏好或推进已读。浏览器确认当前输入框无草稿后刷新原消息页，真实会话加载且具有draggable=true及拖动排序标题。页面自身正常轮询／已读机制沿用原行为。

实现与验证脚本、日志仅留本机忽略目录`.scratch/conversation-order-20261022/`。未进行性能负载测试或生产部署验收。
