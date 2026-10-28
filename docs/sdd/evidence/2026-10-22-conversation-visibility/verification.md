# 会话单方隐藏验证

日期：2026-10-22。关联CAP-MER-006／FEAT-037；engagement 0.2.0、web 0.29.7、supplier 0.3.4。本轮只实现，不提交、推送、更新PR、部署或迁移业务数据库。

## 行为

- 买卖双方会话卡片右键提供“删除对话”，带删除图标、悬停／聚焦反馈。不显示额外隐藏说明，遵循用户后续要求。
- 双方可分别隐藏，数据库保留配对与全部消息、已读位置；另一方列表不受影响。本人未读汇总及商家工作台待回复、近期咨询排除本人隐藏的会话。
- 新持久消息恢复双方可见性；同request_id重放不会撤销隐藏。买家从商品页再次联系通过显式恢复接口恢复本人原会话，保持原配对和历史。GET定位／历史及旧URL不隐式恢复。
- 当前聊天隐藏成功后清空聊天与URL选择，草稿保留；失败保持内容；隐藏成功但列表刷新失败时仍移除卡片。会话切换、迟到历史不会复活已隐藏聊天。菜单键／Shift+F10打开，Esc返回、外部点击／Tab／列表滚动／窗口调整关闭。

## 实际验证

所有数据库命令使用项目Python环境。MySQL设置指定随机`test_engagement_*`库并由测试框架创建、销毁，SQLite使用内存库；均不迁移业务库。

| 命令 | 结果与边界 |
| --- | --- |
| `node --test client/tests/engagement.test.js client/tests/engagement-messages.test.js` | 28项通过；右键／键盘、边界定位、失败草稿、过期响应、隐藏旧URL、显式恢复及既有发送行为 |
| `python manage.py test engagement.tests engagement.test_conversations engagement.test_visibility engagement.test_visibility_migration engagement.test_concurrency supplier.test_workbench --settings=support_ai.test_settings --noinput` | 61项中56项通过，5项真实MySQL专项按条件跳过；内存库销毁 |
| 上述同一测试集合，替换`--settings=engagement.test_mysql_settings` | 61项全部通过，含0001已有配对／消息升级到0002、默认双方可见、真实行锁及连接重建持久化；随机隔离库销毁 |
| `python manage.py check --settings=support_ai.test_settings` | 通过 |
| `python manage.py makemigrations engagement --check --dry-run --settings=support_ai.test_settings` | 无缺失模型迁移 |
| 隔离设置渲染`buyer_messages.html`、`merchant_messages.html`并使用staticfiles finders定位脚本／样式 | 菜单存在、缓存标识更新、资源可定位 |
| `python tools/module_versions.py check`、本次文件空白／冲突标记检查 | 模块归属、版本登记及检查通过 |

首次迁移测试中，历史模型用户投影未包含后续新增昵称字段，随后测试样本账号也超出MySQL的11字符限制；修正测试准备后重新执行上述SQLite／MySQL集合，最终均通过。未修改历史迁移。首次默认沙箱禁止本机MySQL套接字，使用受审权限重试隔离测试成功，未改变数据库连接配置。

实际模板／生产样式／控制器配合独立示例API进行浏览器检查：桌面中文右键菜单只出现删除图标与“删除对话”，操作后当前聊天清空，刷新不恢复示例隐藏会话；Shift+F10可打开菜单。390×844商家阿拉伯语窄屏下菜单显示`حذف المحادثة`，方向RTL，边界位于视口内。示例未发送真实消息、未读取业务会话数据。截图位于忽略目录`.scratch/conversation-hide-20261022/menu.png`及`mobile-rtl.png`，示例标签页和预览服务已关闭，视口已恢复。

## 启用边界

后续用户回复“执行”后已完成本地授权启用，实际备份、迁移、重启与只读检查见[本地启用记录](local-activation.md)。本页“未迁移”等表述记录实现验证完成时的状态。

新增`engagement/migrations/0002_conversation_visibility.py`，为Conversation添加双方各自的布尔隐藏标记。业务环境应用此迁移、服务更新须按[咨询规格](../../modules/merchant-operations/buyer-merchant-conversations.md)单独授权。未做负载测试、未验证生产部署；本轮未更新已有PR #17。
