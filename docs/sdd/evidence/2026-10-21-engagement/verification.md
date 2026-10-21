# 站内咨询与购买后评价验证

日期：2026-10-21。对应 CAP-MER-006／FEAT-037、CAP-CAT-005／FEAT-038。范围为本轮用户确认的咨询、订单评价、商品评分展示、回复与治理，不包含其他 worktree 的拆单／发货修复或支付链路验收。

## 现场与版本

开发分支 `codex/orders-merchant-isolation`，基线 HEAD `25a08ee29e23ce1bd479951e5860b44c9dfb2a89`。本次未提交、未推送、未创建PR、未部署。工作区原有采购页调整、资源清理等改动保留；共享文件只增量编辑，不能将本报告当作整份工作区均可交付的证明。

core 0.6.0、orders 0.2.0、goods 0.5.3、supplier 0.3.1、web 0.25.0，新增 engagement 0.1.0。版本事实源为 versions/modules.json。本地使用 Python 3.9.25、Django 3.2.12、Node。测试不调用模型、外部消息服务或真实支付。

## 实际检查

`<python>` 表示本机已有项目Python环境；未安装或更改依赖。测试日志见同目录文件。

| 检查 | 实际命令／执行方式 | 结果 |
| --- | --- | --- |
| SQLite业务及相关回归 | `<python> manage.py test engagement goods.test_activity goods.test_images goods.test_catalog_pagination goods.test_sales_recommendations supplier.test_store_pages users.tests --settings=support_ai.test_settings --noinput --verbosity=1` | 101项，96通过、5跳过；其中3项要求MySQL行锁，另2项为原有后端条件跳过 |
| 真实MySQL隔离迁移及业务／并发 | `<python> manage.py test engagement --settings=engagement.test_mysql_settings --noinput --verbosity=1` | 36项全部通过，包含3项并发：首次发消息、同购买项评价、不同购买项汇总 |
| 旧版订单向前升级 | 本机隔离脚本，独立随机 `test_engagement_upgrade_*` 库；先迁移至旧orders状态，构造合成订单，再仅向前迁移至最新 | 旧订单金额、数量、商品项保留；buyer_hidden默认false；旧商家快照保持空，评价资格返回HISTORY_NOT_VERIFIED。只移除本次临时库，没有回退数据库 |
| 前端行为 | `node --test client/tests/engagement.test.js client/tests/auth-storage.test.js` | 5项通过；同源标签页身份、重试请求、错误处理、纯文本防脚本渲染、语言偏好 |
| 模块规则回归 | `<python> -m unittest tools.tests.test_module_versions` | 2项通过 |
| 模块归属 | `<python> tools/module_versions.py check` | 16个模块，工作区文件均有归属 |
| Django配置 | `<python> manage.py check --settings=support_ai.test_settings` | 无问题 |
| Migration一致性 | `<python> manage.py makemigrations --check --dry-run --settings=support_ai.test_settings` | No changes detected；历史迁移未修改 |
| 语法 | AST解析本次18个Python文件，`node --check`检查6个JavaScript文件 | 通过；仅为语法，不替代上面的业务及浏览器检查 |
| Diff空白 | `git diff --check` | 通过；仅换行格式提示 |

MySQL测试设置将NAME与TEST.NAME均指向随机 `test_engagement_*`，与配置业务库名比较并拒绝重名；测试库创建／销毁由测试流程管理。SQLite的上传类测试使用工作区下独立临时目录；初次遇到系统沙箱临时目录清理权限错误后已切换并重跑。第一次较宽回归命令还包含不存在的goods.tests标签，最终命令已改为真实模块，上表只列最终成功结果。

## 浏览器操作证据

只使用127.0.0.1:8871上的独立SQLite与合成账号，页面有“隔离功能预览 · 合成测试数据 · 不连接业务库”提示。本地临时启动器及角色切换仅在被忽略的任务目录中，不属于正式路由或交付源码；token为临时合成账号身份，没有使用真实买家／商家会话。新消息、评价及处理记录均未写入业务数据库。

- 买家打开已有会话，发送冲泡问题；商家看见未读、打开并回复；买家返回看见回复及已读。
- 买家在待评价列表选择已完成购买项，填写5星和正文后提交，待评价项消失；商家列表立即出现评价。
- 商家回复评价后，商品详情同页评价区可见回复、购买规格及时间。
- 商品详情4条评价（5／4／3／5星）汇总4.3分，分布正确；筛选当前规格剩3条；评分升序将3星置前。
- 运营端隐藏测试评价后显示不公开及处理记录；随后恢复，处理记录保留。权限、统计和举报幂等另有后端测试。
- 中文、英文及阿拉伯语控件切换；390×844手机聊天按列表／详情切换，阿拉伯语dir=rtl，实测clientWidth=375且scrollWidth=375，没有横向溢出；切换语言保留选中商家标题。已恢复默认浏览器尺寸。

截图：[桌面咨询](messages-desktop.png)、[商品评价](product-reviews.png)、[手机RTL咨询](messages-mobile-rtl.png)。截图中的文字与评价为合成测试内容，不代表真实客户评价。

## 未通过与未执行

- 额外运行的 `tools.tests.test_project_identity` 存量命名检查失败：三份2026-10-20店铺激活证据仍含旧品牌名称。它们相对基线HEAD无Diff，不属于本次功能改动；没有为让检查通过而覆盖旧证据。模块规则测试在工作区临时目录重跑已通过。不能声称整库门禁全绿。
- 业务MySQL未执行新迁移，业务记录未批量改写；未重启业务后端，未运行真实购买、真实支付、完整试单／预售生命周期或容量压测。
- 旧订单没有可信购买快照时暂不可评价或关联订单卡片；普通店铺／商品咨询仍可使用。没有按现商家倒填旧历史，没有自动生成好评。
- 临时预览仅为审阅，不是部署；默认业务服务端口的可用状态没有在本轮认证确认。

## 启用前的具体操作

按项目Git协作规范，业务数据库上线须单独授权。获授权并完成备份后，按迁移依赖执行orders/0003_auto_20261021_1530.py和engagement/0001_initial.py，再更新／重启服务并检查双端真实账号。直接使用旧库启动新订单代码会缺少字段／表，不能跳过迁移。未授权前不得在业务库试跑或自动回退。

本次源码快照绑定见[manifest.json](manifest.json)，其中共享文件可能含保留的其他任务改动；哈希不是提交或暂存授权。
