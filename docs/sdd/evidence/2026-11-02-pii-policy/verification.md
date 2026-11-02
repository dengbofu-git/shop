# PII策略接入及边界验证

日期2026-11-02（Asia/Shanghai）。来源：用户在问答chat明确要求交由功能补全实现，不计入题库；原聊天不改写。基线HEAD为MR31源`591a0ea721414ff33c0c4376282006543b213906`，分支`codex/core-sdd-remediation`。开始时已有R08菜单及LangChain1.3升级增量，本轮保留它们，不自动推送/合入或部署。

## 方案核实

实际锁定langchain1.3.18、langgraph1.2.19、langchain-openai1.7.3；在已有`.scratch/langchain13/runtime`隔离环境核对公开PIIMiddleware构造签名及before_model，确认自定义StateGraph可通过统一文本适配层调用公开钩子，无需create_agent或私有模块。

官方email/credit_card/ip/mac_address检测与redact策略由该钩子实际执行；中文标识/姓名/地址及商品/金额语境由应用规则补充。官方URL能力存在，但未启用全部URL删除，以保留公开知识链接，不能声称URL已全面审查。mask/hash/block能力未用作当前策略，未以声明代替接入。

实际环境`.scratch/runtime-py313`的元数据显示prebuilt1.1.1，但其langgraph/prebuilt/__init__.py不存在，正常及提升权限只读导入均报ToolCallTransformer缺失；不是版本不支持。使用已有隔离pip的`--python`对实际环境仅force-reinstall/no-deps安装同一langgraph-prebuilt==1.1.1；版本未变、未改requirements或其他依赖。随后公开PIIMiddleware导入和pip check通过。日志`.scratch/pii-runtime-repair.log`。未统一重启或确认所有长驻进程载入新实现。

## 覆盖与实际验证

| 表面 | 源码与证据 |
| --- | --- |
| 输入/历史/知识 | pii统一入口替换旧通用检测；原context/history/prepare_evidence调用继续有效；新测试实际检查知识片段及历史读取投影 |
| 外部模型前 | AgentModel处理所有消息角色、内容块及工具字段；测试用捕获客户端验证系统历史、用户、AI历史和ToolMessage均脱敏；既有SDK MockTransport协议回归继续通过 |
| 模型输出/错误 | 普通AI消息及结构化输出字段脱敏，原解析异常正文不传播；新增结构化返回及HTTP错误投影测试 |
| 保存 | commit_turn保存脱敏消息及response；隔离SQLite核对新行无原PII，另构造旧行验证历史投影不回写旧数据库内容 |
| 自定义SSE | frame在JSON编码前递归投影，包含阶段性answer、done及error；测试明确检查嵌套错误文本不泄漏、合法协议UUID不损坏，既有真实回环HTTP/SSE保持 |
| 订单 | prepare_order_input随机引用逻辑保持；新增同轮一致、跨轮随机、伪造引用清理及私有编号不入安全文本检查；原跨买家/隐藏/会话/重放及MCP数据回归保持 |
| Trace/日志 | 复核既有ModelTelemetry仅记录阶段、Token、时延、错误类型及白名单元数据，不增加问答或私有映射日志；既有遥测回归通过 |

所有样本为合成数据，没有业务库访问、真实模型外发、真实历史回放或原始历史批量更新。数值和固定DTO键保持；规范UUID仅在会话/请求控制字段中保留，不放行任意字段字符串。

## 命令、失败与结果

- 新策略前的纯函数样本回归先红，明确复现8个样本失败；新增模型边界/SSE出口检查先红2项。增加协议UUID样本后先红，定位全量流式测试中会话引用误删；修正为仅格式合法协议UUID保留。姓名标签吞掉“喜欢”及黄茶/陈皮误判也分别先红再修正，未把业务失败当预期成功。
- 同批11条敏感样本、12条公开业务样本比较：基线漏检3/11、误改5/12；当前0/11、0/12，详情sample-comparison.json。只证明该合成样本集，不宣称总体中文NER精度、普遍性能或所有未知PII均更好。
- 隔离新依赖环境完整Agent回归347项，339通过/8跳过，无失败，日志`.scratch/pii-final-all.log`；新增知识/结构化结果及茶领域负样本后，以实际解释器最终重跑：`manage.py test support_ai --settings=support_ai.test_settings --noinput`，348项、340通过/8跳过，无失败，14.979秒，日志`.scratch/pii-runtime-verified.log`。
- 测试包含本机LiveServer，需测试套接字权限；数据库由support_ai.test_settings固定到合成SQLite，未连接业务库；provider_calls不涉及真实服务，SDK响应使用测试传输。
- 最后系统检查、模块归属、diff空白及本轮Python静态检查的实际结果见source-snapshot.json；源码和两份测试日志SHA绑定，旧日期证据不改写。

## 限制和交付状态

有限姓氏/动词及茶领域例外并非完整中文NER；复姓、音译、多语言姓名、复杂地址和非大陆电话可能漏检，显式数字语境仍可能歧义。URL保留公开来源用途，不承诺识别其中全部凭据或PII。任意键名或原始用户字典不能当公开DTO序列化；字段最小化及服务端鉴权继续独立执行。官方流式transformer不接管本项目SSE，此处由frame统一处理，模型原始token不前推。

support_ai升至0.32.0，保留前序core0.14.0、web0.36.2增量。本轮未提交/推送、未合入MR31、未统一重启/启用验收、未迁移业务库，不把依赖修复或测试通过称为部署完成。前序LangChain升级/真实模型试验按其独立授权及证据阅读，不继承为本轮真实数据调用授权。
