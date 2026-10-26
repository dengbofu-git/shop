# 报告与历史归档

- [2026-10-26 Grounding真实模型实测](../docs/sdd/evidence/2026-10-26-support-grounding-live/verification.md)：当前DeepSeek配置下的固定合成资料/业务场景，22项符合预期；保留实际输出、用量、耗时和验证边界。
- [2026-10-22 当前工作区基线核验](agent-evaluation/2026-10-22-reports-baseline/README.md)：重新运行相关回归，核对预览日志、HTTP接口、图片清单和历史评测工具的实际关联；包含未通过项与覆盖限制。
- [2026-10-16 Agent 历史归档](archive/2026-10-16/README.md)：六批评测、修改前源码和当天终端记录。
- `agent-evaluation/`：后续 Agent 评测运行输出入口。
- `agent-preview/`：当前终端预览新会话日志入口。
- `tea-images/`、`virtual-products/`：商品图片和模拟商品的专项验证材料，保持现有位置。
- `docs/sdd/evidence/`：按能力与交付批次保留的正式证据，继续由对应 SDD 引用。
- `docs/agent测试文本/`：当前在整理的对话测试材料，本轮不移动在途内容。

运行结果、原始数据、来源快照不是重复源码；不能因为文件与当前实现相同就删除。新评测按运行日期、版本和范围登记，不与旧批次混写。
