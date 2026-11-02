# SDD 提纯静态检查

日期：2026-10-30，Asia/Shanghai。审查结论见[报告](../../product/sdd-purification-review.md)，源码基线为 `0d53d1423cbeb349730ff9462e5798fb5f58cb59`。开始时 `git status --short` 为空；两个已注册 Worktree 仅盘点，本次只修改主目录的 SDD。

## 命令与结果

在仓库根目录执行；使用已有 Python 环境，不安装依赖、不启动 Django 或连接数据库。

```powershell
.\.scratch\runtime-py313\Scripts\python.exe -X utf8 docs/sdd/evidence/2026-10-30-sdd-purification/check.py
git diff --check
```

实际结果记录于[结构化输出](static-audit.json)：检查 YAML 解析及重复键、Markdown 相对路径、MOD／CAP／FEAT 双向主归属、源码路径、两份活动能力文件及 assessment 对齐、清单数量、来源阶段门禁残留和改动范围。逐份现行文档的 SHA256 随结果保存；它们绑定本次文档状态，不证明业务正确性。

最终结构检查退出码0：71份现行文档、12份YAML、249个本地Markdown引用，错误0；数量为8业务域／27能力／36功能／15实现模块。`git diff --check`退出码0。首轮结构检查另发现实现模块旧计数16仍未修正，已按versions/modules.json的15项修正后复验；未以最后一条shell命令的退出码掩盖该轮检查失败。

默认系统 Python 未安装 PyYAML，首次只读解析失败（ModuleNotFoundError）；改用项目已有 runtime-py313 环境执行上述命令。未把失败记作通过，也未修改系统环境。

现有 evidence 未修改；本目录新增审查脚本和结果仅用于复核。本次没有修改运行实现、Migration 或模块版本，没有提交、推送、创建 PR 或部署。业务自动化、浏览器、真实模型、数据库及运行进程检查均未执行；旧验证仍属于各自源码与日期。
