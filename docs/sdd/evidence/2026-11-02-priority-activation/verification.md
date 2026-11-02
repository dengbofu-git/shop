# 高优先级收口与本地启用

日期：2026-11-02，Asia/Shanghai。用户授权“完成上述高优先级，并交付”，包括本地备份/迁移/重启及提交、推送、PR。未授权合入、生产部署或真实支付。持续使用主工作目录及codex/core-sdd-remediation，无新增Worktree；另一已有旧Worktree不作为运行来源，保留其他任务现场。当前源基线c058524749e1c33843ec889f7071ef91d4c70a34，最终SHA及GitHub检查以PR收据为准。

## 本地数据库

- 停止本任务拥有的Web/MCP及清理进程后，确认唯一待迁移为orders.0007_order_currency_snapshot；MySQL8.0.27。
- 完整备份67张表，1,534,644字节；SHA256 `524eaabfcddfa528a4be4ecd5e2ca3f10ce985114efd63f9a6e3472d3146a380`。备份含业务数据，仅保存在主目录`.scratch/high-priority/business-before.sql`，不入库。
- 用与业务容器完全相同镜像的一次性MySQL、tmpfs及随机回环端口恢复；67张表的全部原列、行数及内容摘要完全一致。恢复容器已停止并自动删除。
- 仅应用已授权的0007，无回退或历史迁移改写。迁移后66张原表的原列/行数/内容摘要不变，django_migrations仅新增应用记录；138笔历史订单、137条订单明细currency仍NULL，没有猜测历史币种或换算金额。该迁移已无待应用项。
- 本地日志：`.scratch/high-priority/{backup,restore,applied}.json`及before.json；数据摘要比较发生在迁移当时，不能用服务恢复后正常新增业务否认或外推此结论。

## 统一运行

- `tools/runtime/preview.ps1 -Python .scratch/runtime-py313/Scripts/python.exe -Restart`恢复唯一8000 Web及18082常驻MCP；主目录为唯一应用源，Python3.13.18/Django5.2.18，MCP SDK独立解释器1.29.1。
- `manage.py watch_stock_reservations`独立运行，每30秒处理到期预留；不是另一个网站版本。仅本地后台运行，不代表开机自启。
- 知识Worker旧镜像依赖核验为LangChain0.3，已用当前Dockerfile/requirements/constraints重新构建并替换现有容器；/app只读挂载同一主目录，LangChain1.3.18/core1.7.3/LangGraph1.2.19，与Web一致，pip check通过，ToolNode公开导入通过。
- 默认Docker Hub镜像代理403；使用本机已有官方ECR Python3.13基镜像的构建参数成功，未修改仓库Dockerfile或跳过锁定约束。旧Worker已由Compose替换；不清理数据库、OCR或其他任务容器。
- 最终端口/进程/挂载/健康收据及测试临时服务回收结果见同目录runtime.json；不向仓库写入服务密钥、环境文件或完整进程命令行。

## 本次验证

全部合成测试使用独立SQLite或一次性同版本MySQL、独立Redis；无业务数据夹具、真实金融调用或付费模型请求。以下命令均使用本机当前Python3.13运行环境。

| 验证 | 实际命令/方式 | 结果及范围 |
| --- | --- | --- |
| 阶段集成 | `manage.py test support_ai orders engagement carts supplier inventory logistics goods --settings=support_ai.test_settings --noinput`，CART_TEST_REDIS_URL指向独立Redis DB2 | 622项，606通过/16环境条件跳过，无失败；含PII、任务依赖、推荐、订单、咨询评价、商品及库存；不把SQLite跳过项算通过 |
| 真实后端组件 | 私有mysql_checks.py创建与业务库同镜像无挂载容器，运行orders inventory logistics supplier engagement carts support_ai.test_order_page | MySQL8.0.27，213项全部通过/0跳过，含锁与并发、迁移NULL/金额保持、对象权限及Redis映射；容器已回收 |
| 前端 | `node --test client/tests/*.test.js` | 109项全部通过，包含方案、账号、恢复错误及存储故障等真实处理器回归 |
| 原生MCP | `python -m tools.tea_saas_mcp.agent_integration --resident`，独立MCP解释器 | 19检查通过，实际HTTP SDK→预热Django池，provider_calls=0，cleanup=completed |
| 实际页面+业务API | browser-commerce.cjs→隔离Django完整页面、SQLite、专用Redis | 8项通过：人民币加车、两店结算拆单、取消释放库存、另一店不受影响、合成付款后发货/收货/评价、商品详情评论评分、商品咨询/商家回复、无未捕获异常 |
| 浏览器交互 | browser-interactions.cjs，Edge无头，1440px及390×844视口 | 6项通过：会话键盘菜单、移动断网保留输入及恢复重试、同浏览器账号切换订单/会话隔离、AI历史移出/逐条恢复/重新打开、无未捕获异常；不是实体手机验收 |
| 真实工具输出到页面 | tool_fixtures.py调用实际CP-SAT、query_orders、commit_turn、Redis页映射和attach_order_links，再由browser-tools.cjs受控SSE输入页面 | 订单列表后插入新单，第二笔不偏移、状态实时读取；链接打开真实订单页只显示目标单；390px切方案2成功，bundle哈希保持。业务工具真实，聊天路由/模型为夹具，不宣称真实模型端到端 |
| SSE浏览器 | `node tools/tests/support_stream_browser.cjs <本次Django渲染页面>` | 7检查通过，进度、未保存部分文本、done后卡片、同request_id重试、错误清除、账号变化中止、无异常；受控合成SSE |

原始日志、脚本及截图在主目录`.scratch/high-priority/`；source-snapshot.json保存本次指纹。浏览器验收初稿暴露的是测试路径/选择器/账号初始化覆盖/未等待载入的夹具错误，修正后重新生成上述最终通过记录；没有据此修改生产业务。MCP初次把SQLite模式与性能采样混用导致知识搜索失败，标准resident模式重跑19项通过；未把不适用的性能采样记作通过。

## 仍未覆盖及交付边界

- 真实支付到账、退款、渠道对账和跨币种结算仍开放；历史NULL币种继续人工核验。
- 真实模型推荐质量、全部跨语言/全部AC、所有实体终端和高并发生产容量不由本次测试证明。候选裁剪、未知运税费及日志/聊天保留策略按现行SDD保留限制。
- 本地迁移已应用；代码回退不可替代数据库恢复。备份已实际恢复验证，但恢复本地业务库属于单独操作，不能自动覆盖服务恢复后的新数据。
- 本次修改support_ai0.32.2/0.32.3及相应测试/文档，统一交付原分支已有依赖/菜单等增量；目标main；同步时已核实MR32由外部合入main（f1f65ab0d1c4c99c0ec2150c4288da4321d88790），正常合并后源码树与已验收9483517一致，本次18文件增量另建PR，不重复交付旧MR内容。未合入时本地收尾为waiting-merge，不创建重复MR、不删除他人Worktree。
