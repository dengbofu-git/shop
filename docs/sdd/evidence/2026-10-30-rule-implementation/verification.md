# R01/R02、R05/R06/R08/R09 实施与隔离验证

日期2026-10-30，Asia/Shanghai。持久主工作区（物理目录见本机现场），分支 `codex/core-sdd-remediation`，HEAD基线 `0d53d1423cbeb349730ff9462e5798fb5f58cb59`。工作区含此前SDD提纯及首批权限/真实性修复；本次保留它们及“场景”chat产生的场景文档，不覆盖原证据。当前未提交，HEAD不能复现本轮增量，源码字节另列于source-snapshot.json。

## 本轮行为与验证对应

| 规则 | 实现与边界 | 主要证据 |
| --- | --- | --- |
| R01/R02 | 必要偏好失败只阻断依赖它的推荐任务，独立本人订单继续、提交partial并可幂等回放；纯不可见订单、身份及会话越权保持拒绝，失败依赖按原执行器跳过 | support_ai.test_mcp_data、test_task_tools、test_semantic_planning及既有执行器回归；纯必要偏好故障仍不保存成功轮次 |
| R05 | OrderInfo/OrderGoods.currency新建CNY；0007先加无默认可空列，再设应用默认，历史NULL和原金额不变；原币种/未知投影、CNY统计及支付人工核验保护 | orders.test_currency在SQLite及MySQL8.0.27验证历史订单和明细；admin_panel.test_overview、supplier.test_order_actions及前端真实渲染器回归 |
| R06 | public_skus含公开零库存，sellable_skus追加正库存；网站和Agent/MCP详情共用公开范围，隐藏或停用商家不可读；加车/推荐/结算保留库存校验 | support_ai.test_product_details、goods既有用例及交易回归；网站图片文件服务保持兼容，不用图片授权替代详情资格 |
| R08 | 本浏览器移出、撤销、已移出列表逐条恢复；先持久本地状态再改页面；不DELETE数据库问答 | client/tests/support-history-restore.test.js执行实际事件处理器，覆盖存储写入失败、恢复失败、账号变化和列表切换；服务端历史回归保持 |
| R09 | 私有Redis当前页绑定买家/会话，最多20项、TTL24小时；提交后发布、Lua拒绝旧写、SQL最新序列核对；位置选中后重查归属/隐藏及实时状态 | support_ai.test_order_page使用真实隔离Redis，覆盖插入、状态变化、隐藏、越界、到期、外人/会话、服务故障、失败提交、重放/迟到写、空页、下一页替换及新页缓存写失败；语义规划检查订单位置不误判商品位置 |

Redis方案由用户明确回复“采用 Redis 方案”确认，见[ADR0011](../../../adr/0011-displayed-order-page-redis.md)。本场景及边界已按用户要求发送“场景”chat记录；该消息不构成业务库启用或Git交付授权。

## 实际命令和结果

解释器为 `.scratch/runtime-py313/Scripts/python.exe`，Python3.13.18、Django5.2.18。所有测试使用合成账号/订单；未连接业务库测试，未调用真实模型、支付或承运商。

- `manage.py test support_ai orders pays carts goods supplier inventory logistics users engagement --settings=support_ai.test_settings --noinput`：617项，564通过、53因数据库/组件条件跳过，无失败，55.129秒。SQLite隔离测试，包含回环HTTP/SSE及临时图片目录；本机沙箱初次阻止临时目录/网络操作，改为经自动审批的测试权限执行。日志 `.scratch/rules-integration-final.log`。
- 最后追加的CNY交易金额保护、结算DTO及历史明细迁移断言：`manage.py test orders.test_currency admin_panel.test_overview supplier.test_order_actions --settings=support_ai.test_settings --noinput`：31项，30通过、1跳过，无失败。日志 `.scratch/rules-currency-final.log`。
- `manage.py test orders.test_currency support_ai.test_order_page logistics.test_scope supplier.test_analytics --settings=rules_mysql_settings --noinput`：28项全部通过，无跳过。临时配置只指向本任务新建、无业务挂载、随机回环端口的MySQL8.0.27及Redis7.4.5；MySQL版本与本地业务后端一致。0007的隔离迁移断言同时核对历史订单及明细NULL/金额保持。日志 `.scratch/rules-mysql-currency-items.log` 与 `.scratch/rules-check/real-component-tests.log`；测试库及两个临时容器均由夹具退出清理。
- `node --test <client/tests/*.test.js逐个文件参数>`：105项全部通过，无跳过。日志 `.scratch/rules-frontend-last.log`。执行买家/商家订单渲染、原币种/未知投影、咨询历史真实处理器、结算及既有看板回归。
- `python -X utf8 tools/tea_saas_mcp/agent_integration.py --resident`：19项通过，临时SQLite业务/知识夹具，实际HTTP MCP SDK→预热Django进程池，provider_calls=0，cleanup=completed。MCP解释器 `.scratch/runtime-mcp313/Scripts/python.exe`，SDK1.29.1；日志 `.scratch/rules-mcp.log`。
- `tools/module_versions.py check`：15模块，所有工作区文件均有归属。`manage.py makemigrations --check --dry-run --settings=support_ai.test_settings`无模型差异。`git diff --check`通过；修改及新增Python/JavaScript语法、6份模板编译、9份YAML解析通过（精确文件哈希及静态检查计数见source-snapshot.json）。`python -m unittest tools.tests.test_project_identity -v`4项全部通过；首次发现本证据引用物理旧目录名，已改为本机现场说明，不改物理目录。只读核对本任务夹具标签的容器列表为空。

早期综合检查发现序号正则误匹配“第二个商品”，已限制订单后缀并增加回归；图片接口额外范围限制影响原图片占位语义，已保留原文件服务行为，只限制公开详情。中间失败与最终通过分开记录，不用语法检查替代业务验证。

## 交付与未覆盖范围

模块版本：core0.13.0、goods0.7.4、orders0.6.0、pays0.2.2、admin_panel0.4.3、supplier0.4.4、support_ai0.30.0、web0.36.0；保留首批inventory0.2.2、logistics0.1.2及其独立证据。

未提交、推送、新建PR、合入或部署；未迁移业务库，未重启后端/MCP/清理进程。运行服务仍是先前加载版本，禁止将当前源码测试通过称为已启用。启用前须单独授权备份/应用orders.0007，再从统一来源重启；旧代码回退不等于安全回退业务数据，不自动反向迁移。

本证据是定向及阶段集成证据，不代表CAP-AI-003全部15项AC已完成实机与整体验收。真实浏览器键盘/移动端操作、真实模型语义质量、真实支付/退款/渠道币种及生产容量未验证；Q-011、Q-013除当前页临时映射以外的范围保持开放。Git policy正式推送门禁须在获交付授权、提交、同步最新main后执行；当前不把旧HEAD的策略结果当作未提交增量验收。
