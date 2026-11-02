# LangChain 1.3真实模型合成测试

2026-11-02用户明确要求“调用真实模型进行测试”。按本轮授权使用当前有效配置：DeepSeek `deepseek-flash`，服务域名 `api.deepseek.com`，配置revision6。沿用已升级的LangChain1.3.18、core1.7.3、OpenAI适配器1.7.3、SDK2.54.0。

仅发送本次新编问题、合成3000元预算及程序Schema/提示词，不读取或发送真实用户历史、偏好、订单、库存或商品资料。配置表仅读取模型标识，测试阶段不修改业务数据。外部请求累计6次，SDK自动重试为0，没有因为测试误报而重复已发出的调用。

## 结果

| 测试 | 新编输入 | 实际结果 | 耗时 |
| --- | --- | --- | --- |
| 普通回复 | 请用不超过100字说明绿茶和红茶在加工上的主要区别，不谈健康功效。 | 非空中文文本，包含两类加工差异，SSE正文58个非空回调分片；未对表述进行茶学标准逐句审校 | 2.539秒 |
| 总预算短答 | 合成待补充问题：人民币3000是每件还是整套；回答“总的” | `scope=total, scope_only=true` | 1.909秒 |
| 单件预算短答 | 同上；回答“不是总的，是每件” | `scope=unit, scope_only=true` | 1.033秒 |
| thinking + JSON | 同上；回答“不是每件，是全部加起来” | 请求携带thinking enabled及json_object，解析为`total/true`，usage完整；不记录或展示隐藏推理文本 | 1.207秒 |
| 多意图顺序 | 先介绍红茶和绿茶的区别，再推荐两款红茶。 | 按顺序提取question_answering、recommendation，推荐limit=2，两段quote逐字来自输入；只提取任务，未查询业务商品 | 0.765秒 |
| 中英阿混合改写 | Compare black tea 与 dark tea 的加工区别 في السعودية | QueryTranslations调用及解析返回，usage完整；初版脚本未及时保存翻译正文，翻译质量未完成验收 | 1.385秒 |

6次协议交互均完成：实际路径为`/chat/completions`、stream=true、stream_options.include_usage=true、max_tokens正确且未发送max_completion_tokens，on_llm_end各触发1次。输入合计2879 Token、输出492 Token，无unknown_usage或provider_overrun。请求耗时合计8.838秒，不含本地准备、脚本排查和文档整理；不是性能基准，也不代表生产并发性能。

普通文本首个非空正文回调约1.142秒，thinking JSON约1.162秒。function_calling参数通过工具分片返回，非空正文token计数为0，不能用该计数判断未流式返回或未执行。

## 测试脚本问题及复核

首次脚本在普通调用后关闭LangChain缓存的HTTPX共享连接，使后续5项在发送前失败；当时真实外部请求仅1次。修正脚本生命周期后，只续发尚未发送的5项，总量仍为6次。没有改动生产客户端来绕过问题。

初版脚本还错误要求所有调用都产生非空正文Token，导致function_calling的4项被标为AssertionError。根据已保存的请求参数、usage、回调结束事件及Schema结果离线复核：2条scope与多意图语义断言通过；混合改写的解析完成，但正文缺失，未补作一次外部请求或宣称翻译语义通过。

因此最终口径为：**6项协议完成，5项输出内容可核验，1项翻译内容记录不足**。原始记录保留在本机`.scratch/langchain13/real-results.json`、首次脚本记录及恢复日志；经复核的无凭据数据见[真实结果JSON](real-model-results.json)。

## 验收范围

本轮直接调用项目`configured_model`适配器、真实预算范围分类与查询改写函数，检验升级后实际SDK通信和解析；没有完整运行买家登录、向量召回、重排序、数据库商品推荐、下单或整轮MCP业务执行。因此不将本轮结果称为完整RAG或推荐准确率验收。thinking测试调整的是单次合成评测的请求预算，不修改平台配置。

没有新增功能实现、Migration、版本发布、提交、推送或生产部署。
