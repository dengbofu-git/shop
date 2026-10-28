# 套餐／整套预算范围补充

2026-10-26，support_ai 0.21.4；分支codex/orders-merchant-isolation。无前端或数据库结构增量，未提交／推送。

## 问题与改动

- 只读核对截图咨询保存状态：“套餐”“整套”失败后仍保留CNY3000、pending、budget_scope及原金额来源；不是金额丢失。原范围规则要求“整套预算”等更长表述，不支持裸套餐／整套，模型后备路径失败。后续明确“推荐总价3000块的套餐”也因通用套餐范围遗漏而失败。
- 在纯契约层统一完整范围短答词表，供有限范围提取与证据校验共同使用；语义规划仍要求当前pending推荐且确实缺budget_scope。无有效任务不复活旧预算；带否定或额外购买条件不能被短答规则吞掉。
- 明确总价的剩余词“套餐”作为通用范围处理，茶叶套餐、红茶套餐保持已有茶类；复合属性或包装要求不能忽略。

## 隔离验证

`python -X utf8 manage.py test support_ai.test_colloquial_budget support_ai.test_colloquial_budget_graph support_ai.test_total_budget_generic_tea --settings=support_ai.test_settings --noinput -v 1`

19项全部通过，Django检查0问题；仅隔离SQLite默认测试库，未使用业务MySQL／AI PostgreSQL／Redis或真实模型。包含：

- 当前金额与原茶类、接近模式在套餐／整套等短答后保留；单价分支继续清除组合模式。
- 真实保存会话→recent_context→短答→实际商品组合工具，用合成SKU得到3000元方案。
- 保存一次模拟旧规划失败→再回答整套，仍能通过真实来源校验并返回组合；不依靠手工拼造上下文替代存储投影。
- 明确“推荐总价3000块的套餐”通过真实合成SKU查询；原截图总价茶问句继续通过。
- 无待补充问题、否定、额外茶类／件数等不被快捷规则擅自解释。

## 本地依赖检查

原咨询只读回放尝试读取当前偏好时，127.0.0.1:5433连接超时；Docker容器列表和Desktop状态查询也无响应，因此没有把该次真实上下文回放写成通过。此连接问题与预算规则问题分别记录。

用户已另行明确允许重启整个Docker Desktop恢复本地依赖；不执行数据库迁移、不改用户历史，也不把原对话发送到外部模型。恢复及回放的实际结果在完成后补记。

## 恢复与真实保存上下文核验

- 正常Docker Desktop restart超时仍未退出旧进程；按用户明确授权，核验安装路径后仅结束旧Docker Desktop／backend进程并隐藏重新启动。容器／数据卷及配置保留。PostgreSQL5433、Redis及观测容器恢复健康。
- 项目实际default配置仍为127.0.0.1:3306；原master容器restart-policy=no，退出后未自动恢复，因此启动同一容器，不改接其他项目的13306实例。
- 重新只读确认default与ai_storage均可连接；使用截图时已保存的原咨询上下文、当前合法偏好、model=None回放，套餐／整套两者均为source=rules、tool=recommend_bundle、budget=3000.00、currency=CNY。没有写入回放轮次，也未向任何模型服务发送历史。
- 19项隔离回归在补齐“每件商品的预算／整套商品的总预算”等完整选择表述后再次全部通过。5文件AST、16模块归属及定向差异空白检查通过。
- 16:46重启原本地Django预览，PID20352替换为40832，清除Docker恢复前的旧连接并加载support_ai 0.21.4。客服页面只读GET返回200；启动配置检查0问题。既有ai_storage未应用迁移提示保留，本轮没有执行迁移。
