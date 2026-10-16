# 商家智能助手 · 0.1.0

入口：商家工作台侧栏「智能助手」，页面 `/merchant_assistant.html`。

本版本只提供模块注册、页面和商家身份校验后的状态接口，聊天输入处于禁用状态。
沿用 Django 模板、原生 JavaScript、AuthStorage Bearer Token 和全站主题；后续模型编排
沿用仓库已有 LangChain/LangGraph 依赖，0.1 不加载模型、不装配任务图或业务工具。

- `GET /v1/merchant-ai/status/`：活跃商家／供应商可读，返回模块版本和空能力清单。
- 没有聊天、上传、商品写入或媒体生成接口，没有业务模型和数据库迁移。
- 会话、记忆及买家客服任务不与 `support_ai` 混用。
- 设计、合同、验收与后续扩展位置见 [0.1 方案](../docs/商家智能助手.md)。
