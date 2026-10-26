# Grounding真实模型实测：run-01

2026-10-26，使用当前配置deepseek-flash、thinking=enabled、配置修订5及项目真实模型适配器。

19个固定场景全部符合预先写明的预期。其中16个场景实际调用模型，3个非法来源/新增数字/文档冒充业务事实场景由程序先行拦截。共25次真实模型请求，输入18061 Token、输出12969 Token，各场景累计94.117秒。

- [manifest.json](manifest.json)：冻结输入、预期、配置、安全数据范围和源码指纹。
- [results.jsonl](results.jsonl)：逐场景、逐模型调用的实际结构化输出、判定、用量与耗时。
- [summary.json](summary.json)：本批统计和测试期间源码指纹一致性。
- [procedure.md](procedure.md) / [procedure-sha256.json](procedure-sha256.json)：本批实际运行的临时脚本及指纹；复测需选择新目录，不覆盖本批。

知识源、商品和订单均为固定合成夹具；真实的是模型服务、配置及应用校验/图代码。完整人工复核、额外篡改场景和边界见[统一报告](../../../docs/sdd/evidence/2026-10-26-support-grounding-live/verification.md)。
