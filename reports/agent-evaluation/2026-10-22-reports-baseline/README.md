# 2026-10-22 reports 当前工作区基线核验

本批按用户要求，以当前工作区重新测试并记录，核对 reports 与命令、脚本及关联 HTTP 接口的真实关系。基线包含已有未提交改动，不能当作远端 main、发布版本或整体上线验收。

- 基线 HEAD：`25a08ee29e23ce1bd479951e5860b44c9dfb2a89`；分支：`codex/orders-merchant-isolation`。
- 测试开始时登记版本：support_ai 0.15.0、goods 0.6.1、core 0.7.0、web 0.29.4；完整模块和实际文件哈希见 [baseline.json](baseline.json)。核验期间检测到范围外的站内咨询页面与 web 版本增量（至 0.29.5），漂移见 workspace-integrity；相关后端与客服前端源码未变化，最后另复测买家页面壳 3 项通过。
- 环境：项目 Conda Python 3.9.25、Django 3.2.12；`support_ai.test_settings`，default 与 ai_storage 均为隔离 SQLite 内存库。
- 相关既有回归：127 项，123 项通过、4 项失败。另有 9 项功能与缺陷复现探针、4 项当前契约核验及 2 项归档契约检查通过。缺陷复现通过不表示被测工具没有缺陷。
- 当前确有预览日志输出和图片登记能力；网页客服使用数据库，不自动读取或写入这些预览日志。旧评测工具存在归档前路径、固定人工结论和版本标识问题。
- 本批未调用真实模型、未写入业务库、未执行 MySQL 造数或浏览器端到端验收；不据此报告模型效果或整站验收通过。

完整关系表、失败分析和限制见 [核验报告](../../../docs/sdd/evidence/2026-10-22-reports-baseline/verification.md)。

| 文件 | 用途 |
| --- | --- |
| [baseline.json](baseline.json) | 测试开始时的 HEAD、版本、工作区状态和 1240 个路径的哈希或缺失状态 |
| [checks.json](checks.json) | 实际命令、环境修正、退出码、耗时和日志位置 |
| [related-regression.log](related-regression.log) | 初次运行原始日志，含沙箱临时目录权限问题，保留原样 |
| [related-regression-local-temp.log](related-regression-local-temp.log) | 改用工作区临时目录后的 127 项回归结果 |
| [current-probes.log](current-probes.log) / [probe-observations.json](probe-observations.json) | 9 项功能关联与缺陷复现探针、实际观察 |
| [current-contract.log](current-contract.log) / [current-contract-observations.json](current-contract-observations.json) | 对 4 项旧断言按当前人民币与任务规则重新核验 |
| [archive-contract.log](archive-contract.log) | 205 份旧归档内容及当前对照输入路径检查 |
| [django-check.log](django-check.log) | Django 系统检查 |
| [final-buyer-shell.log](final-buyer-shell.log) | 检测到范围外页面/版本漂移后的 3 项买家页面及客服入口复测 |
| [module-ownership.log](module-ownership.log) / [index-diff-check.log](index-diff-check.log) | 模块归属及本批索引文档 diff 检查 |
| [preview-command/](preview-command/) | 本次 CLI 实际生成的合成问候会话 JSONL，零模型调用 |
| [procedures.md](procedures.md) | 实际执行的临时探针源码和复测方法；作为证据保存，不接入业务运行 |
| [workspace-integrity.json](workspace-integrity.json) | 测后与基线的文件比对、本批索引文档增量、范围外并发漂移及暂存区一致性 |

本批与 2026-10-16 的原始输入、输出和人工记录相互独立；没有覆盖旧报告或将历史成绩改写成当前成绩。
