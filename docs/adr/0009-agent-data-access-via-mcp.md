# 0009 模型 Agent 的数据访问入口统一使用 MCP

Status: accepted
Date: 2026-10-28
Decision makers: 项目用户（本轮明确指令）
References: [访问规范](../sdd/architecture/agent-data-access.md)、[项目改造清单](../sdd/modules/ai-support/mcp-migration.md)
Supersedes: none
Superseded by: none

## 背景与问题

项目已有独立 Python 环境的 stdio MCP 商品详情工具，但买家 Agent 仍在 Django 内通过本地函数读取商品、订单、知识、偏好和历史。仅增加 MCP 包装并保留 Agent 直调路径，会形成两套数据入口，难以统一权限、输出和故障行为。商家助手尚未开放模型能力。

## 决定及确认依据

用户明确要求：“模型 Agent 的数据访问入口统一使用 MCP，写入sdd，并且检查整体项目有哪些部分需要修改”。据此接受 MCP 为模型 Agent 的唯一数据入口；包含宿主为模型主动取得的持久上下文。由宿主控制工具选择及可信身份，后端 Python 领域服务保留查询和业务规则。最终 Agent 路径移除直接数据服务调用及本地降级。

本决定没有要求普通网页 API、PDF Worker 或管理程序统一改走 MCP，也没有授权交易写工具、自动写记忆或开放商家模型聊天。认证、幂等、revision、会话保存及运行配置仍属宿主控制职责。具体边界以访问规范为唯一正文。

## 方案与取舍

选择“统一 MCP 入口、复用可信后端服务”。不选择长期保留 MCP／本地双入口，避免权限及失败语义漂移；不删除后端业务函数，避免在 MCP 协议层重写订单、库存与检索规则。

代价是增加协议调用、进程／连接生命周期、授权上下文和预算传播成本。现有 Python 3.12 MCP SDK 与 Python 3.9 Django 分环境方式可作为迁移起点，但 stdio 或常驻受控服务、最终 HTTP 认证和部署方式仍须实现验证，不由本 ADR 宣称完成。

## 影响与验证

规范覆盖推荐、详情、订单、RAG、偏好、历史及预览；保持价格、订单选择、知识权限和只读边界。本决定补充现有架构，不撤销原订单、检索或 PDF ADR 的业务规则。

决定补录时仅完成静态盘点与规范更新。随后用户要求“运行”，0.24.0／0.9.0已完成应用入口源码迁移和隔离协议／实际后端验证，见[运行设计](../sdd/modules/ai-support/mcp-runtime.md)与[证据](../sdd/evidence/2026-10-28-agent-mcp/verification.md)。没有迁移业务数据、重启已有服务或发布；接受架构和隔离验证均不等于业务启用、完整CAP验收或物理凭据隔离。
