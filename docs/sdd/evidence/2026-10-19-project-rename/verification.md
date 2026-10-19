# tea_saas 工程命名验证

日期：2026-10-19，Asia/Shanghai。开发分支为 `codex/core-tea-saas-rename`。本次修改未暂存、未提交、未推送或部署；已有 Redis 配置及同时出现的 Agent 语义规划改动继续保留，不能将完整工作区差异都归为本次命名任务。

## 实现

首轮规范化覆盖 295 份 UTF-8 文件，工程包、MCP 包、Skill 目录及历史源码快照目录完成改名；随后补齐默认配置、数据库目标校验、命名回归、文档和版本。当前受管理文件名和 UTF-8 内容中的旧工程标识与旧中文品牌残留为零。扫描不包含 Git 历史、私有环境、依赖、缓存、二进制图片或工作区根目录本身。

用户单独授权两份历史迁移的默认邮箱文本改名，除此以外不修改历史迁移。没有执行数据库迁移、种子数据命令或真实模型评测，也没有修改数据库中的账号或邮箱。Git 迁移不可变门禁保持原样，未运行提交门禁并声称通过；本次用户授权记录不自动变为 Hook 例外。

模块版本在当前工作区已有版本上递增，详见 `versions/modules.json` 和各模块 changelog。当前工程包、变量及升级边界见[有效规格](../../modules/platform/project-identity.md)。

## 实际检查

业务 Python 使用本机现有 Conda 解释器，MCP 使用 `tools/tea_saas_mcp/.venv/Scripts/python.exe`。以下 Python 命令均以对应解释器执行，工作目录为实际仓库根目录；本机环境没有改名。

| 命令或检查 | 结果 |
| --- | --- |
| `python manage.py check --settings=support_ai.test_settings` | 通过 |
| `python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings` | No changes detected；未执行迁移 |
| `python manage.py test users goods carts orders pays news inventory logistics supplier admin_panel merchant_ai --settings=support_ai.test_settings --noinput` | 63 项，2 项跳过，其余通过 |
| `python manage.py test goods.test_seed_identity --settings=support_ai.test_settings --noinput` | 2 项通过：库名或服务器 UUID 不匹配时均在读用户／写数据前拒绝 |
| `python manage.py test support_ai.test_product_details support_ai.test_telemetry.AgentTelemetryTests --settings=support_ai.test_settings --noinput` | 15 项通过 |
| `python -m unittest discover -s tools/tests -v`（新增命名测试前） | 28 项通过，包含已有 Redis 配置的 3 项测试 |
| `python -m unittest tools.tests.test_project_identity tools.tests.test_module_versions -v` | 4 项通过，覆盖命名扫描、入口和未暂存目录改名归属 |
| MCP Python：`python -m unittest tools.tea_saas_mcp.test_server -v`，`TEA_SAAS_TEST_PYTHON` 指定本机业务解释器 | 9 项全部通过，包含 SDK stdio → Django 命令 → 临时 SQLite 完整链路 |
| `node client/tests/*.test.js`（逐文件调用，不由 Node 展开通配符） | 9 组全部通过，见[结果](frontend-tests.json) |
| `python client/tests/tea-saas-contract.py` | 25 个页面壳及退役路径、资源和 SDD 契约通过；旧路径预期 404 |
| 当前受管理 Python AST、前端 JavaScript `node --check` | 258 份 Python、55 份 JS 通过，见[结果](syntax.json)；语法不等于业务验收 |
| 三份 Compose：`docker compose --env-file .env.postgres -f <文件> config --quiet` | AI 存储、重排、监控配置均通过，未输出展开后的配置或凭据，未执行重新编排 |
| Skill `quick_validate.py .agents/skills/tea-saas-change-delivery` | 通过 |
| `python tools/module_versions.py check`、`git diff --check` | 模块归属及空白检查通过 |

初次受限环境运行时，临时目录 ACL 造成图片／Git 测试 PermissionError，Windows asyncio socketpair 初始化阻塞 MCP。相同相关检查在获准的本机隔离测试环境重跑后通过；没有关闭测试或削弱断言。

## 完整回归的当前失败

按模块清单枚举 `test*.py`（排除测试设置模块），使用 `support_ai.test_settings` 运行内存 SQLite 全部 Django 回归：174 项，14 个 failure、4 个 error、5 项跳过，未全通过。日志见[当前回归](django-regression.log)，实际工作区和 Python 环境路径已替换为占位符。

失败涉及当前 Agent 的 `SemanticPlan` 与旧模型替身约定、推荐／知识组合、偏好与澄清预期，以及管理页响应为空。工作区同时存在语义规划实现变化，本轮保留这些变化，没有为了命名任务改写相关业务或放宽测试；也未在另一份完整基线上证明所有失败均属历史问题。因此只报告上述定向检查通过，不宣称整站回归通过。

## 本地预览

`http://127.0.0.1:8000/login.html` 返回 200；浏览器刷新后可见 `tea_saas` 标题、图片替代文字和品牌。标准 Django WSGI 加静态文件处理提供本地页面预览；无自动重载。[截图](login-preview.png)记录当前界面。

常规 `manage.py runserver` 启动时连接业务 MySQL 失败：本机 MySQL80 服务停止，当前 Windows 账号无法打开服务进行启动。未改用另一项目数据库、未重建业务库。已有本项目 PostgreSQL、Ollama 和重排容器已恢复；本次没有验证模型就绪或真实调用。业务数据库恢复前，登录与商品 API 的真实业务联调未通过，需以管理员权限启动原有 MySQL80 后再使用常规开发启动命令。

已有四类 Docker 卷已通过本机忽略的环境文件显式绑定，卷和账号实际名称保持原样；没有创建、删除、重命名或迁移数据卷。

## 历史证据规范化

[规范化清单](normalization-manifest.json)保存首轮替换前／后的文件摘要及原路径摘要。清单中的 `normalized_sha256` 描述第一轮规范化内容；`current_sha256` 描述本轮收尾时文件内容，可能包含后续修订或并行已有改动。历史报告内保留的旧 SHA 不代表规范化后的文件摘要；本轮未重跑那些历史评测。
