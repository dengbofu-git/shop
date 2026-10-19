# 2026-10-16 Agent 历史归档

归档日期：2026-10-19。本目录保存旧版评测和终端材料，不代表当前版本已通过相同验证。

| 材料 | 归档入口 |
| --- | --- |
| 任务编排基线与对照 | [planner](agent-evaluation/2026-10-16-planner/) |
| 分组推荐 | [grouping](agent-evaluation/2026-10-16-grouping/) |
| 混合说明与推荐 | [mixed-tea](agent-evaluation/2026-10-16-mixed-tea/) |
| 查询改写与多路检索 | [rag-rewrite](agent-evaluation/2026-10-16-rag-rewrite/) |
| 多轮推荐追问 | [dialogue-followups](agent-evaluation/2026-10-16-dialogue-followups/) |
| 15 组场景 | [scenarios15](agent-evaluation/2026-10-16-scenarios15/) |
| 当天终端日志与诊断 | [agent-preview](agent-preview/) |

[manifest.json](manifest.json) 逐项登记原路径、归档路径和原始 SHA256。归档文件原字节保留，包括旧命令、历史路径、当时失败和已知限制；不把历史输出改写为当前结果，也不删除证明前后状态相同的重复证据。

当前 `support_ai/evaluation/compare.py` 和 `report.py` 的默认资料入口已调整到本目录。归档内的旧运行脚本及原始数据仍记录当时路径；复现旧布局时可按 manifest 的 `original` 字段，将副本恢复到单独的临时复现目录，不能覆盖正在开发的工作区。真实模型、业务读取或数据库调用仍需单独核对授权和环境；归档不授予运行权限。
