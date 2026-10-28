# Python 3.13 / Django 5.2 升级验证

日期：2026-10-28。范围为第一阶段运行时和必要配套依赖升级；保留数据库引擎、AI 主版本、页面结构和业务契约。运行基线为 Python 3.13.18 / Django 5.2.18。

本次未提交、推送或创建 PR。基线提交为 `63fa850843771dde21c7bd49ed9bc98019e5d24a`，测试对象为其上已有商品导入／MCP 等工作与此次升级组成的工作树，不将基线 SHA 冒充最终提交。30 个升级文件的 SHA256 见 [源码清单](source-manifest.json)，结果与依赖版本见 [验证数据](validation.json)。

## 实际结果

| 检查 | 结果及边界 |
| --- | --- |
| Windows 业务回归 | 最终 Python 3.13.18 下 509 项，493 项通过、16 项按原条件跳过 |
| Linux 业务回归 | Python 3.13.18 / Django 5.2.18，断网临时容器、合成配置、内存数据库；同组 509 项，493 项通过、16 项跳过 |
| MySQL 真实后端 | 随机隔离测试库完整建库／迁移／回归／清理，147 项通过；覆盖库存预留、幂等下单、支付验签、商家订单、咨询／评价和商品导入 |
| PostgreSQL / pgvector | 随机隔离测试库迁移和检索回归，11 项通过 |
| 解析边界 | 58 项，54 项通过、4 项按环境条件跳过；本地 HTTP 模拟，不调用外部视觉／语言模型 |
| 页面脚本 | 25 个 Node 测试文件，93 项通过；页面结构与前端依赖未升级 |
| 本地真实 MCP 传输 | 最终主工作区运行时通过 16 项检查，实际 SDK stdio → Django 后端；合成数据、隔离 SQLite／PostgreSQL，外部模型调用 0 次，测试资源已清理 |
| Django 检查 | 配置检查无问题；`makemigrations --check --dry-run` 无差异，没有新增或改写历史 Migration |
| 依赖与脚本 | Windows 80 个安装包一致性检查通过；Linux Worker `pip check` 通过；11 个本轮 Python 文件 AST、PowerShell 启动器语法和 `git diff --check` 通过 |
| 本地启用 | Web 8000 与知识库 Worker 均为 3.13.18 / 5.2.18；登录、商品、客服页面及静态脚本均返回 200；重启后实际监听 PID 与元数据一致 |
| 模块归属 | 16 模块，全部工作树文件有归属；本轮升版 core 0.10.0、support_ai 0.24.1、goods 0.7.2、engagement 0.2.3、ai_storage 0.7.2，保留已有 changelog |
| 治理回归 | 29 项中 28 项通过；1 项既有商品导入证据的旧路径命名检查失败，见下文，不能称全部门禁通过 |

SQLite 条件跳过不代表数据库特性验收；MySQL 和 PostgreSQL 的真实后端结果单独列出。真实 DeepSeek 调用、真实支付扣款、真实用户历史回放、OCR GPU 推理没有执行。GitHub Actions 新增 Python 3.13 合成业务回归任务，但本次没有推送，不能声称该远端任务已经运行。

## 数据和运行核对

- MySQL 仍为原 `127.0.0.1:3306` 实例，版本 8.0.27；只读核对 14 个用户、135 个 SPU、120 个 SKU、138 笔订单。本次没有改动或换库。
- PostgreSQL 仍为原 `127.0.0.1:5433` 实例，版本 16.15，路由负责的 AI 迁移无待办；Redis 原连接 PING 成功。未修改引擎镜像、嵌入空间或向量数据。
- 按数据库路由过滤后，MySQL 仅存在另一任务既有的 `goods.0012_productimportjob` 待办，本次未启用。Django runserver 会把路由到 PostgreSQL 的四份 AI 迁移也计入默认库警告，不能据此在 MySQL 执行 AI 迁移。
- Worker 切换前未发现运行中的导入任务。新容器只读双库连接和解析配置检查通过，启动后无重启；OCR、重排序、Ollama、数据库及其他项目容器没有重建。
- 原 Worker 镜像保留为本机 `tea-saas-knowledge-worker:pre-py313-20261028`，旧 Python 环境及升级前文件备份保留。本地新解释器为 `.scratch/runtime-py313/Scripts/python.exe`，预览元数据在 `.scratch/runtime/preview-8000.json`。

## 问题发现与修正

1. 首轮 252 个请求测试错误来自隔离设置在测试发现阶段修改共享 `DATABASES` 字典，新 Django 读取请求事务配置时缺少默认字段。改为独立复制设置后，保留原断言的 509 项回归通过；没有给生产请求伪造字段或降低隔离条件。
2. NumPy 原生扩展在 `patch.dict(sys.modules)` 恢复后不能重复导入。测试在模拟 Paddle 前显式导入 NumPy，解析模拟回归全部达到原预期，没有改变生产推理行为。
3. 本机 Docker 的原镜像代理返回 403。构建通过 Docker 官方 Python 镜像的 ECR Public 分发地址完成，使用 Dockerfile 已有 `PYTHON_IMAGE` 参数，没有更改全局 Docker 配置或数据库镜像。
4. Windows venv 启动器会派生真正监听端口的解释器子进程。启动器现核对父子关系和命令，记录实际监听 PID；实际安全重启及 HTTP 检查通过。

## 既有检查阻塞

`tools.tests.test_project_identity` 发现 `docs/sdd/evidence/2026-10-28-product-import/verification.md` 含退役工程名称的本地执行路径。这份文件在此次升级前已存在于未提交商品导入工作中；未擅自改写其他任务的验收证据，也未弱化检查器。本轮新增与修改文件不含该退役标识。该项仍需在后续整合交付前处理。

## 验证命令

以下 `python` 均指最终独立 Python 3.13.18 解释器；Node 为现有 22 系列。

```text
python manage.py check
python manage.py check --settings=support_ai.test_settings
python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings
python manage.py test orders inventory pays carts goods supplier engagement users support_ai --settings=support_ai.test_settings --noinput -v 1
python manage.py test orders.test_reservations orders.test_reservation_contracts pays.test_reservation_signatures supplier.test_order_actions engagement users.test_nickname inventory goods.test_product_import --settings=engagement.test_mysql_settings --noinput -v 1
python manage.py test ai_storage.test_hybrid_search ai_storage.tests.VectorStorageTests --settings=pg_settings --noinput -v 1
python -m unittest ai_storage.test_paddle_document ai_storage.test_vision ai_storage.test_pdf_vision ai_storage.test_pdf_parser_protocol
python -m tools.tea_saas_mcp.agent_integration --postgres
node --test client/tests/<各测试文件>.test.js
python -m unittest tools.tests.test_git_policy tools.tests.test_module_versions tools.tests.test_project_identity -v
python tools/module_versions.py check
git diff --check
```

`pg_settings` 为 `.scratch/upgrade-20261028/pg_settings.py`，只使用随机名隔离 AI 库。运行脚本、原始日志及升级前文件位于本机 `.scratch/upgrade-20261028/`，共享清单只记录日志 SHA256；不将本地配置、凭据、历史会话或物理路径复制为公开证据。升级工作区用于保护既有未提交工作，尚未提交，继续保留。
