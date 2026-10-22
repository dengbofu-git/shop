# 消息、指标和店铺身份交付验证

日期：2026-10-22。DELIVERY_ONLY，复用`codex/engagement-delivery`的干净工作树，初始源与主干均为`a5e978836e9e3316d24c4204fd7dbe1178c03a4e`。最终集成web0.29.6，其他本机阶段版本如下。最终提交与主干SHA记录于PR正文。

## 交付范围

- web0.29.4：消息页视口布局、回车发送及输入法保护、空列表欢迎语；数量输入与内嵌加减；买家账户菜单定位、动画、单项高亮和键盘操作；Agent指标说明按需显示；成交价格区间CNY单位和对齐。
- users0.4.1：商家不再提供昵称编辑，昵称PATCH仅买家本人可用，资料GET提供当前店铺名。历史商家昵称不清除，买家昵称保留。
- supplier0.3.3：价格分布所需的本店只读销售洞察接口及现有成交归属过滤函数；本店历史价格、付清资格、商家隔离及两位小数金额。
- engagement0.1.4：补充买家会话列表使用店铺名的回归断言，无咨询运行逻辑变化。首次提交门禁将该测试文件计入模块实现范围并要求升版，补齐版本／changelog后按正常Hook重提，未绕过门禁。
- 未纳入其他聊天的人民币统一计价、AI推荐、资源清理、首页精选及经营概览／待办等独立改动。公共文件按具体增量提取，原开发工作区保持原样。价格分布使用CNY统计不等于全站计价改造。

## 本轮实际验证

以下命令在交付工作树运行，Python使用`python`，测试环境变量仅用于测试进程；工作树不复制业务配置文件。

| 命令／检查 | 结果 |
| --- | --- |
| `node --test client/tests/engagement.test.js client/tests/engagement-messages.test.js client/tests/product-detail-summary.test.js client/tests/merchant-insights.test.js client/tests/profile-nickname.test.js` | 43通过 |
| `python manage.py test users.test_nickname engagement.test_nickname supplier.test_insights --settings=support_ai.test_settings --noinput` | SQLite内存隔离库24通过，框架创建销毁 |
| 同标签，`--settings=engagement.test_mysql_settings --noinput` | 随机名称独立MySQL测试库24通过，框架创建销毁；不在业务库试跑 |
| Django `check`与实际模板渲染 | 通过，消息页布局／缓存、所有工作台脚本引用、只读店铺字段、买家昵称保留、Agent资源、销售洞察区域均核对 |
| Django静态资源查找 | 新增菜单／消息布局／价格图样式、控制器及统一logo可找到 |
| `python tools/module_versions.py check`、`git diff --check` | 通过 |
| 数量模板完整片段核对后重跑`node --test client/tests/product-detail-summary.test.js` | 9通过，模板及数量行为均覆盖 |

首次独立验证器未向子进程加载本机环境变量，出现缺少`DJANGO_SECRET_KEY`，模板检查也遗漏设置测试模块；仅修正忽略目录内的验证器，按上述隔离设置重跑后通过，未修改业务配置或绕过检查。

## 验证边界

### 主干正常同步后的复验

提交后主干前进到`4a71b0826fc21cbbec6722b8b11362981d1943bd`，含已合入PR15人民币计价／推荐改动。本分支正常merge，17处冲突均为模板资源缓存号或版本说明；模板保留主干资源引用并刷新本轮菜单／数量资源号，模块清单保留主干其他版本并提升本轮四模块，changelog保留双方记录。本机账户菜单阶段0.29.1归入最终0.29.4，避免覆盖主干同号人民币兼容记录。JS业务逻辑由Git正常合并，未重写主干金额功能。

合并后重新运行上述43项Node测试、SQLite24项、隔离MySQL24项及模板／Django检查，均通过；另执行`node --test client/tests/checkout.test.js client/tests/storefront.test.js`两组检查通过，覆盖金额切换、采购车／确认页与店铺渲染兼容。未重跑与本轮无关的真实AI调用。Git规范门禁将在完成merge提交后绑定最终源SHA执行。

merge提交门禁相对第一父提交也要求web递增；因此最终集成版本为0.29.5，新增对应changelog，未绕过检查。补充的是交付版本元数据，业务验证覆盖的实现没有再次变化。

实现阶段已分别进行消息页、数量、价格分布、账户菜单、指标提示、商家资料与欢迎语的示例浏览器检查，证据在各模块文档及对应忽略截图目录。交付阶段核对原实现与选取内容，并以交付工作树执行上述测试／模板检查；未在最终工作树重做完整浏览器端到端、生产负载或真实模型调用。没有新增迁移，不重复执行业务库迁移，不重启或部署服务。源SHA的Git规范／语法门禁与远端CI结果以PR及交付工具实际输出为准。

首次远端CI命名检查发现三份验证文档的本机解释器路径包含旧工程名称；将命令规范为当前激活环境的`python`后，重跑同一命名／模块归属回归。不修改业务实现或绕过检查。

文档修复后，pre-push再次检测到主干前进，故正常合并已合入PR16的商品卡片链接。保留主干链接与本轮视口布局、欢迎语、Enter发送，统一缓存参数，最终集成web0.29.6；合并后重新执行Node定向测试、Django模板及项目命名回归。后端业务文件相对此前MySQL／SQLite复验未变化，保留其24项结果。
