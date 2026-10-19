# SDD 引用检索

从仓库根目录使用现有 Python 3.9 或更新解释器运行，无需安装依赖、启动 Django 或连接数据库：

```powershell
python tools/sdd_refs.py CAP-AI-003
python tools/sdd_refs.py RULE-AI-003-01 --limit 20
python tools/sdd_refs.py CAP-CAT-004 --include-evidence
```

- 搜索范围固定为本仓库 `docs/sdd/` 下的 `.md`、`.yaml`、`.yml`、`.json`，默认排除其顶层 `evidence/`；`--include-evidence` 可加入历史证据。
- ID 必须是大写字母数字组成、以字母开头且至少含一个连字符的标识，例如 `MOD-AI`、`CAP-AI-003`、`Q-009`、`AC-AI-003-01`。按字面量完整匹配，`CAP-AI-003` 不匹配 `CAP-AI-003-01`、`CAP-AI-003-A` 或 `CAP-AI-003_extra`。
- 输出仓库相对 `路径:行号: 文本`，文件按路径排序，行号从 1 开始。默认最多显示 500 个命中行；`--limit` 指定正整数上限，超出时明确显示截断及总命中行数。
- 固定从脚本位置定位仓库，不受当前工作目录影响；不跟随符号链接或目录连接，不搜索 `.scratch/`、业务数据或依赖目录。
- 退出码 `0` 表示有命中（含明确标记的截断），`1` 表示扫描完整但无命中，`2` 表示参数、目录、读取或 UTF-8 解码错误；读取失败不得当成“无引用”。

检索结果可能包含历史、草案和引用示例，必须打开对应文档核对效力。命中不证明存在有效定义，无命中也不证明可以删除某项业务。该工具不验证 YAML Schema、权限、SDD 阶段或验收状态。

工具归属 `core`，实现为 [sdd_refs.py](../../tools/sdd_refs.py)，边界回归为 [test_sdd_refs.py](../../tools/tests/test_sdd_refs.py)。适配思路参考 Store 的引用检索，使用本项目 Python 标准库重新实现，不引入其完整检查器或阶段政策。
