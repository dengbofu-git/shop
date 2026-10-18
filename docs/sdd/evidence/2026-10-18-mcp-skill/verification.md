# MCP 与交付 Skill 验证记录

日期：2026-10-18（Asia/Shanghai）。工作分支 `codex/users-unified-login`，基础 HEAD `19b5f0b094305e7fd56c628729611dea8eb7317c`。结果对应未提交工作区的本次增量，不能将基础 HEAD 当成包含实现的交付 SHA。工作区有其他任务的已有改动，未暂存、提交、推送、创建 PR 或部署。

## 本次实现

- `core 0.1.11`：仓库级 dadashop-change-delivery Skill、本地 stdio MCP 适配器、独立依赖环境、接入说明和搜索设计草案。
- `support_ai 0.11.1`：公开商品详情服务、固定管理命令、站内详情工具复用及定向测试。
- 只读取在售且正可用库存的公开商品，库存沿用账本优先／无账本回退口径。属性使用公开白名单，SQL 投影不含成本和商家身份字段。
- 无数据库迁移。search_products 尚未实现，设计见 [详细草案](../../modules/ai-support/search-products-design.md)。

## 通过项目

| 验证 | 实际命令和结果 |
| --- | --- |
| Skill 结构 | `python -X utf8 C:/Users/dbf/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/dadashop-change-delivery`：Skill is valid |
| Django 行为 | `E:/miniconda/envs/dadashop/python.exe manage.py test support_ai.test_product_details support_ai.test_planning support_ai.test_task_tools.TaskToolIntegrationTests.test_one_product_and_dependent_live_details --settings=support_ai.test_settings --noinput`：22 项通过，系统检查无问题 |
| MCP 协议和桥接 | 先设置 `DADASHOP_TEST_PYTHON=E:/miniconda/envs/dadashop/python.exe`，再运行 `tools/dadashop_mcp/.venv/Scripts/python.exe -m unittest tools.dadashop_mcp.test_server -v`：9 项通过，无跳过 |
| 模块清单 | `python tools/module_versions.py check`：15 模块，已跟踪文件均有归属；另对本次新增路径调用 owner 匹配，均有归属 |
| 静态检查 | `git diff --check` 通过；本次新增 Python 文件 AST 解析通过；新增文本未发现冲突标记 |

Django 测试覆盖严格 SKU ID、可售范围、账本优先和多仓合计、账本耗尽不回退、价格／库存实时更新、公开字段和 SQL 投影、属性脱敏及白名单、SELECT 查询无写入、JSON 命令与异常脱敏，以及站内依赖详情任务。SQLite／LocMem 由测试设置覆盖真实数据库与缓存，不调用模型。

MCP 测试覆盖官方 SDK 握手与工具发现、结构化和文本结果、未知工具拒绝、额外字段／布尔值／浮点数拒绝、固定子进程命令、无后端配置、坏输出和后端失败、超时／取消后的进程回收。完整链路在临时文件 SQLite 中迁移并创建合成商品，实际运行 stdio → MCP → Django 命令 → 数据库；随后将合成库存置零，下一次调用返回 no_match。该数据库由测试创建并清理，未连接业务库。

Skill 还人工核对了三个授权场景：只实现时不提交；只提交已有改动时不扩展业务修复；只推送时要求干净现场和主干同步，不自动创建 PR。结构校验与人工审阅不代表模型行为评测已完成。

## 相邻回归的已有失败

首次运行以下较宽范围回归共 30 项：28 项通过，1 项失败、1 项错误。

```powershell
E:/miniconda/envs/dadashop/python.exe manage.py test support_ai.test_product_details support_ai.test_task_tools support_ai.test_planning --settings=support_ai.test_settings --noinput
```

- `test_invalid_hard_conditions_commit_only_safe_clarification`：期望 HTTP 200，实际为 503。
- `test_saved_preference_quote_is_canonicalized_only_after_owner_verification`：响应缺少 recommendation_status，触发 KeyError。

核对方式是在独立测试进程中读取 `git show HEAD:support_ai/tool_services.py`，将修改前源码编译并加载到内存中的同名模块，再运行上述两个测试；两项以相同方式失败。没有覆盖工作区文件或修改测试预期。这证明上述失败在修改前工具实现与当前其他工作区文件组合下也存在，不能称相邻回归全部通过；本次未修复条件抽取／澄清问题。

## 环境与覆盖边界

Django 使用 Python 3.9.25；MCP 使用独立 Python 3.12.9 与 SDK 1.29.1。Windows 受限沙箱内 asyncio 启动阻塞，已中止阻塞进程，并在获准的沙箱外本地测试环境完成协议测试。最初 venv 的 ensurepip 失败后，使用 uv 向同一隔离目录安装依赖，未修改 Django 环境。

未验证真实 MySQL 的聚合执行计划或并发库存、真实模型质量、公共网络认证或用户当前会话的 MCP 自动加载；没有新增 HTTP 服务，也没有改用户级 Codex 配置。接入配置示例见 [接入说明](../../../MCP与Skill接入.md)。由于没有提交／推送，本次不执行针对已提交交付对象的 pre-push 检查，也不声称 GitHub 远端门禁或发布完成。
