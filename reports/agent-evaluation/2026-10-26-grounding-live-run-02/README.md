# Grounding真实模型实测：run-02

2026-10-26，使用与run-01相同的真实模型配置，补充3个直接篡改业务候选回答的场景：金额/币种/库存、两款商品价格互换、订单付款发货状态及送达承诺。

3个场景均被真实模型明确判为safe=false；生产等价的最终拦截逻辑均返回安全兜底，没有放行错误事实。共3次模型请求，输入1064 Token、输出526 Token，各场景累计5.467秒。复核模型的修订稿只作为观察保存，没有拿修订稿替代程序事实发布。

- [manifest.json](manifest.json)：配置、源码/脚本指纹和调用上限。
- [results.jsonl](results.jsonl)：工具事实、篡改候选、真实模型判定、修订稿和最终拦截结果。
- [summary.json](summary.json)：本批统计和测试期间源码指纹一致性。
- [procedure.md](procedure.md)：实际运行脚本；参数为 `--business-only`。生产安全提示词由当前workflow.py的字面量提取，未另外设计更有利的提示词。

完整结果及适用边界见[统一报告](../../../docs/sdd/evidence/2026-10-26-support-grounding-live/verification.md)。
