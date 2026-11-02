# 统一PII文本策略

2026-11-02，用户授权的实现交接，不新增问答题库。保留StateGraph和受控工具，不改订单鉴权、推荐算法或状态机。

## 官方能力及接法

锁定LangChain1.3.18的公开`langchain.agents.middleware.PIIMiddleware`，通过公开`before_model`钩子对独立HumanMessage文本副本执行redact；不调用私有_redaction接口，不改成create_agent。启用官方email、Luhn信用卡、IP和MAC检测；保留中文占位契约。中文相邻ASCII片段分段处理，避免词边界漏检。不删除全部URL，因为公开知识来源链接是业务数据，不能宣称URL中所有PII均已检查。

中文补充大陆手机、证件、账号、姓名/地址标签、有限姓氏+业务动词语境及未知长数字。明确商品/SKU编号8至12位、金额和日期保留；手机/证件和官方检测先执行，商品标签不能豁免实际PII。信用卡标注语境另做保守过滤，即使Luhn不通过也不直接外发。规则不是中文NER，复姓、音译、复杂省略、地址及非大陆电话仍存在歧义/漏检；茶名、陈皮等已知业务主体保留，正负样本持续维护。

## 覆盖路径

| 路径 | 实际处理 |
| --- | --- |
| 输入/订单 | prepare_order_input先生成本轮随机引用和私有映射，再redact；随机性、同轮一致性、伪造清理、电话卡号保护和本人/会话鉴权保持 |
| 历史/知识 | context/prepare_evidence等沿用入口；history_value和终端safe_record直接复用redact_value，协议UUID与嵌套PII策略一致，历史GET只读取投影，不批量改写原行 |
| 外部模型 | AgentModel在SDK调用前处理所有角色消息、内容块和工具字段，覆盖语义规划、检索改写、证据审核、安全审核，不只最后一个用户消息 |
| 模型返回 | 普通content/附加字段/正常及invalid_tool_calls和结构化字段投影；解析错误固定文案，不将原解析正文抛给业务错误 |
| 保存/公开结果 | finalize投影response，新commit_turn脱敏user_text/response后保存；私有active_order_id与Redis映射不进入公开对象，旧行不重写 |
| HTTP/SSE | _response及frame递归投影文本值，阶段性已核验结果和最终done/error都在编码前过滤，不先泄露再替换；仍不输出模型原始token |
| 日志/Trace | 继续运行元数据白名单，不保存问答、私有映射及异常正文，不把中间件当日志收集器 |

redact_value保留数值和固定Schema键；conversation_id/request_id只有格式有效的规范UUID作为协议值保留，任意文本不因字段名放行。应用仍须使用固定公开DTO白名单，不能直接序列化任意用户字典。

公开方案身份为`bundle-`加12位小写十六进制哈希；长数字回退规则须保留这一完整格式，保证文本、模型JSON、历史与方案按钮一致。保留只作用于未知号码回退，实际手机/卡号/邮箱仍先检测；错误长度或字符不放行，格式不授予跨账号/会话访问权。2026-11-02后续反例和验证见[交付后记录](../../evidence/2026-11-02-pii-delivery-followup/verification.md)。

2026-11-02后续复核：显式phone/mobile/receiver_mobile/email/receiver/recipient/real_name/full_name/address/id_card等私人联系字段按字段语境投影，避免整数手机号或裸姓名绕过文本检测；不以通用name/id键判定个人信息，商品名称、sku_id、金额/数量继续保留。空值及布尔标志不伪装成联系人文本。历史/终端投影只复制结果，不修改传入对象或真实历史；[后续证据](../../evidence/2026-11-02-pii-surfaces/verification.md)。

官方输出/工具处理默认关闭，其Agent流式transformer不会自动处理本项目Django SSE；本实现显式覆盖各路径，不能将导入中间件等同全路径保护。

## 来源链接中的明确敏感信息

HTTP(S)链接先在本地解析，userinfo或明确敏感query/fragment参数（访问令牌、密钥、签名、邮箱/手机等），以及路径/参数解码后能由既有规则识别的PII，整条投影为“[敏感链接]”，避免留下可用令牌。普通公开来源不改字符串、不重编码，现有应用内文档及订单固定路由保持。复用官方/中文检测，最多处理两层编码及100个参数，解析失败保守移除；不访问URL或做DNS查询。

这只补明确凭据/可识别PII，不代表所有URL均被审核：未知参数中的随机秘密、更多编码层、非HTTP及任意相对URL等不在完整识别承诺内，也不是SSRF防护。敏感签名链接不能再点击，原私有来源由受权后台处理。[本轮验证](../../evidence/2026-11-02-pii-urls/verification.md)。

## 启用及验证

2026-11-02后续已完成本地统一重启，当前support_ai0.32.3在Web/MCP加载，知识Worker依赖也已更新；622项集成回归及浏览器SSE等结果见[收口证据](../../evidence/2026-11-02-priority-activation/verification.md)。下段仅描述早先安装修复时点。

见[验证记录](../../evidence/2026-11-02-pii-policy/verification.md)。实际运行环境同版本langgraph-prebuilt1.1.1缺少入口文件，已仅重装该锁定包，通过公开API导入及pip check；未升级其他依赖。未统一重启服务、迁移业务库、回放真实历史或调用真实模型，安装修复不等于运行启用验收。

官方依据：[Middleware](https://docs.langchain.com/oss/python/langchain/middleware/built-in#pii-detection)、[Guardrails](https://docs.langchain.com/oss/python/langchain/guardrails#pii-detection)；实际API另以锁定版本导入、源码和回归核对。
