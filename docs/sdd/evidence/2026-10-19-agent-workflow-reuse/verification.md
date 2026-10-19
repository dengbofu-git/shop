# 任务、领域约定与 SDD 引用检索验证

日期：2026-10-19（Asia/Shanghai）。类型：本地工具与文档验证。实现模块：`core 0.3.1`。本次不修改业务规则、CAP 阶段、Migration 或发布状态。

验证时分支为 `codex/core-tea-saas-rename`，HEAD 为 `566e4709dfd55ddba138eb4a2c41523838352bc7`，存在既有工程命名、业务和页面等未提交工作；HEAD 不能单独复现本次工作区。本次增量涉及 `CONTEXT.md`、`docs/agents/`、`docs/adr/README.md`、引用检索脚本及其测试，以及 AGENTS、README、SDD 入口、忽略规则和 core 版本资料。文件摘要见 [manifest.json](manifest.json)，摘要不包含本验证记录自身。

## 实际验证

| 命令／检查 | 结果与覆盖 |
| --- | --- |
| `python -m unittest tools.tests.test_sdd_refs -v` | Python 3.12.9：7 项中 6 通过、1 跳过；完整 ID 边界、中文与 BOM、行号、格式与目录范围、历史证据开关、排序与截断、参数错误、无匹配、读取／解码失败 |
| 现有业务 Python 3.9.25，参数 `-X utf8 -m unittest tools.tests.test_sdd_refs -v` | 同组 6 通过、1 跳过；使用实际已有解释器，不安装依赖或改名环境 |
| `python tools/sdd_refs.py CAP-AI-003 --limit 3` | 退出码 0，输出 3 行及截断／总行数说明 |
| `python tools/sdd_refs.py CAP-CAT-004 --include-evidence --limit 2` | 退出码 0，可显式加入历史证据；开关范围另由合成夹具验证 |
| 从 `tools/` 运行 `python sdd_refs.py RULE-AI-003-01 --limit 1` | 退出码 0，定位到同一仓库 SDD，不依赖当前目录 |
| 业务 Python 3.9.25，参数 `-X utf8 tools/sdd_refs.py RULE-AI-003-01 --limit 1` | 退出码 0，真实 SDD 检索成功 |
| `python tools/module_versions.py check` | 通过：15 个实现模块，当前工作区文件都有归属；本次新增根文件与工具均属于 core |
| `git check-ignore .scratch/sdd-reuse/spec.md` | 通过：本机任务记录默认忽略 |
| `git diff --check -- AGENTS.md .gitignore README.md docs/sdd/README.md versions/modules.json versions/changelogs/core.md versions/README.md` | 通过；已有 LF／CRLF 提示不构成检查错误 |
| 新增 6 份规范文档的 Markdown 本地链接、冲突标记与模块归属检查 | 通过；目标文件存在，归属 core |
| 两个新增 Python 文件按 Python 3.9 语法解析 | 通过；实际 Python 3.9 执行见上 |

真实符号链接测试因当前 Windows 宿主不允许创建测试链接而跳过，未宣称真实链接／目录连接场景验收通过。默认宿主临时目录首次测试不可写，随后将合成测试夹具改至已忽略的仓库 `.scratch/`；两种 Python 环境均完成测试及夹具回收。

## 验证边界

引用命中仅说明文本位置，不能证明规则有效、Schema 自洽、业务正确或能力获准推进。术语入口是现有来源的索引；ADR 仅建立格式，没有补造已批准决定。本地分诊标签不等于 GitHub 配置或并行执行授权。

未执行 Django 业务测试、真实数据库、模型调用、浏览器验收或全量回归，本次变化不涉及这些运行路径。未提交、推送、创建／合入 PR、部署或发布；保留其他既有工作。
