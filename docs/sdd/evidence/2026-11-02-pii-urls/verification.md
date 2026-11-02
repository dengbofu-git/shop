# 继续逐项处理：来源链接中的隐私

日期2026-11-02，Asia/Shanghai。用户要求继续处理，复用codex/core-sdd-remediation；HEAD仍为MR32源c058524749e1c33843ec889f7071ef91d4c70a34，开始时已有公开bundle引用修复未提交，保留原增量及证据。

## 问题与处置

旧策略刻意不删除所有URL以保留公开知识来源，但明确access_token、userinfo及百分号编码邮箱仍能沿模型/历史/HTTP/SSE泄露。合成新测试3项先跑11个失败子项，证明既有出口确有遗漏，不是单凭文档推断。

现在对文本中的HTTP(S)链接先做本地解析，发现userinfo、非空的明确令牌/密钥/签名/联系方式参数，或路径及query/fragment解码后能被现有PII规则识别的信息，则将整条链接替换为“[敏感链接]”。处理在通用检测前，避免先替换邮箱而留下可用账号或令牌。普通无敏感信息链接保持原字符串，不重编码正常query；应用内固定文档/订单引用路由保持。

复用官方检测和既有中文模式检查解码值，不引入私有库接口；编码处理限定两层，参数数目上限100，解析失败保守移除候选链接。只解析本地文本，不发HTTP/DNS请求。明确参数字段及规则见support_ai/pii.py；普通任意短字符串不因包含“token”字样而删除，仅URL参数键和值语境生效。

## 验证与边界

- `manage.py test support_ai.test_pii_urls support_ai.test_pii_policy support_ai.test_pii_surfaces support_ai.test_pii_bundle_reference --settings=support_ai.test_settings --noinput`：21项全部通过，日志`.scratch/pii-url-green.log`；对应修复前`.scratch/pii-url-red.log`。
- 增加二层编码参数名、重复令牌、SPA回调fragment、编码手机号及引用文本后，`manage.py test support_ai --settings=support_ai.test_settings --noinput`：358项，350通过/8按组件条件跳过，无失败，23.218秒，日志`.scratch/pii-url-full.log`。实际Python3.13/Django5.2/LangChain1.3环境，SQLite合成测试库及本机HTTP/SSE，无真实模型/业务库调用。
- 最后补实际claim_sources→HTTP来源DTO检查，确认保留资料标题/年份、移除来源凭据且不修改原证据对象；该新增测试以最后定向命令单独验证，不把此前358项说成包含这项新测试。结果及源码/日志SHA见source-snapshot.json。
- 系统检查、15模块归属及diff检查通过；本轮2份Python AST及相关文件哈希另见source-snapshot.json。未重跑前端及原生MCP全套，因本轮未改页面或协议实现，不复用旧结果冒充新执行。

本修复只针对HTTP(S)显式凭据/可识别PII。不能识别所有未知参数名下的随机秘密、任意加密/编码、非HTTP协议或所有相对URL；不是通用URL安全审计或SSRF防护。敏感签名链接会不可点击，原始私有来源需由受权后台处理，不能把凭据继续发给模型/客户端来保持链接可用。固定DTO、最小字段及独立鉴权仍保留。

最后收口：新增实际来源DTO投影的定向回归54项全部通过，日志`.scratch/pii-url-final-targeted.log`。补充编码“黄茶喜欢”业务负样本后先复现误判，再使URL内部判断复用实际替换结果而非只看正则匹配，尊重既有茶领域例外；最终完整Agent回归359项、351通过/8跳过，无失败，14.323秒，日志`.scratch/pii-url-verified.log`。该最终运行覆盖全部本轮新增测试，不把较早358项成绩混用。系统、模块归属、2份AST及diff检查通过，日志/源码哈希随证据保存。

support_ai本地版本0.32.3；包含此前0.32.2未提交修复。MR32不含这些后续增量，本轮未提交/推送、合入、迁移数据库或重启启用。中文NER、全AC和实机验收等剩余边界保持，不因一个遗漏修复声明全部完备。
