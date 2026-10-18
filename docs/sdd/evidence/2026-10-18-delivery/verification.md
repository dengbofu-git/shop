# 跨模块更新交付验证

日期：2026-10-18（Asia/Shanghai）。用户授权更新SDD及模块版本说明，并提交、推送和创建面向main的PR。本次汇总当前工作区各聊天已实现的产出，保留未实施功能和已知缺口，不执行合入、发布、部署或业务库迁移。

## 交付范围和版本

统一登录与平台权限、商家和管理员销售口径及交易总览、商品分页与卡片、标签页身份和商家预览、历史咨询、公开详情MCP、项目交付Skill、跨境茶叶SaaS定位及SDD对账。退役报关／溯源页面及初始化命令，历史Migration和数据不改。

当前模块版本为core0.2.0、users0.2.2、goods0.4.1、orders0.1.3、supplier0.2.0、admin_panel0.4.1、support_ai0.11.1、web0.14.1；其余保持清单基线。web0.14.1仅同步页面契约测试的当前SDD数量25／34，不变更业务行为。完整15模块表见[版本总览](../../../../versions/README.md)。

版本总览和README已按modules.json同步，历史版本章节保留；当前SDD为8域25能力34功能15实现模块，CAP-AI-003保持SPEC_REVIEW、商家助手仍仅入口、知识库提交仍禁用、search_products仍为设计。

## 本轮实际验证

| 范围 | 命令与结果 |
| --- | --- |
| Django定向回归 | `E:/miniconda/envs/dadashop/python.exe -X utf8 manage.py test users.tests admin_panel.test_overview supplier.test_analytics goods.test_catalog_pagination support_ai.test_product_details support_ai.test_planning support_ai.test_telemetry merchant_ai.tests support_ai.test_task_tools.TaskToolIntegrationTests.test_one_product_and_dependent_live_details --settings=support_ai.test_settings --noinput`：79项，78通过、1失败；系统检查无问题 |
| 前端行为 | `node client/tests/<文件>.test.js`，覆盖admin-shell、auth-storage、buyer-catalog-preview、buyer-products-pagination、cart-currency、merchant-product-preview、tea-saas-brand、unified-login：8个脚本通过 |
| 页面外壳 | `E:/miniconda/envs/dadashop/python.exe -X utf8 client/tests/tea-saas-contract.py`：25页面、退役入口／资源、当前SDD映射检查通过 |
| 商品接口和分页 | `E:/miniconda/envs/dadashop/python.exe -X utf8 client/tests/catalog-preview-contract.py docs/sdd/evidence/2026-10-18-delivery/catalog-contract.json`，再运行`node client/tests/buyer-catalog-preview.test.js`并传该文件：合成目录30件接口契约和分页通过 |
| MCP | 设置`DADASHOP_TEST_PYTHON`为业务解释器，使用独立环境运行`python -m unittest tools.dadashop_mcp.test_server -v`：9项通过，含stdio→Django→临时SQLite完整链路、取消和超时回收 |
| 文档和模块 | 12份SDD YAML、能力／功能双向引用、模块与版本表、文件和文档链接静态核对；`python tools/module_versions.py check`、Diff与Git policy检查按交付对象执行并在PR记录最终命令结果 |

完整本轮输出分别保存于 [Django](django-tests.json)、[前端](frontend-tests.json)、[MCP](mcp-tests.json)。Django与目录测试使用隔离SQLite／LocMem及合成账号，不连接业务库、Redis或真实模型。MCP因Windows沙箱asyncio限制在获准的本地沙箱外运行，仍只使用临时合成库。首次目录验证因沙箱临时目录权限失败，改在工作区证据目录输出同一合成数据后通过；没有修改业务查询。

## 失败和未覆盖

`support_ai.test_telemetry.AgentOperationsTests.test_platform_page_contains_settings_and_monitoring`期望直接GET `/admin_agents.html` 包含`agent-settings`，实际该地址按当前管理外壳设计302到`/admin_panel.html#agents`，响应正文为空。当前内容页为`/admin_agents.html?embedded=1`。保留该失败，不更改业务路由或跳过测试；相关嵌入模板由页面外壳契约及前端路由测试分别覆盖，不能据此把79项写成全通过。

已有两项推荐条件澄清回归失败记录见[此前MCP验证](../2026-10-18-mcp-skill/verification.md)，本轮未重跑为新通过。历史分页／身份切换完整交互、订单404／脱敏／重放、RAG质量、真实MySQL／PostgreSQL聚合和并发、真实支付／退款／物流／订阅计费均未在本轮验收；不因PR创建而提升阶段。

## Git交付边界

当前只有主工作区，沿用codex/users-unified-login。先核对实际Diff及所有新增文件归属，精确暂存本次产出；无新增Migration。提交后刷新origin/main并正常merge，运行`python tools/git_policy.py verify --base origin/main`，绑定最终源SHA和mainSHA后推送。最终SHA、主干同步结果、PR链接及远端检查状态以PR和最终交付消息为准，避免把尚未产生的SHA写成已完成。

未执行强推、自动stash、历史重写、hook绕过、合入或部署。创建PR不等于GitHub已启用必需检查／保护规则，也不代表当前已知失败被解决。
