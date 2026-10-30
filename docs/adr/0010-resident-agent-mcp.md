# 0010 常驻MCP服务与请求级DataSession

Status: accepted
Date: 2026-10-29
Decision makers: 项目用户（明确要求实现）
References: [ADR0009](0009-agent-data-access-via-mcp.md)、[常驻设计](../sdd/modules/ai-support/mcp-resident.md)
Supersedes: none
Superseded by: none

## 背景与确认依据

0.25.0分段测量显示每轮SDK和Django进程启动占合成首次查询大部分耗时。用户询问为何不能在后端启动时启动；在说明“常驻独立服务、预先初始化Django、每轮独立授权和DataSession”的方案后，用户明确回复“实现”。据此分开服务生命周期与请求生命周期，不改变ADR0009的数据唯一入口及领域权限。

## 决定与取舍

应用默认使用本机Streamable HTTP MCP服务。SDK服务启动即预热有界Django进程池；进程跨请求复用，每轮签名grant建立独立DataSession并独占一个进程，结束后清理会话及数据库连接再归还。常驻服务不是共享买家会话。

HTTP控制面由服务共享密钥认证；买家身份由签名grant及后端逐工具归属／revision复验决定。当前仅监听127.0.0.1，沿用同机签名文件通道，不涉及互联网暴露或交易写入。

独占租约保留既有检索预算和状态边界；默认2个进程，可配置1—16个。宿主等待回答模型时仍占用租约，不是最终吞吐模型；满池返回可重试BACKEND_BUSY，不在提问路径临时扩容或回退数据库。保留显式stdio兼容，不在HTTP失败时自动切回。

单机开发启动器先确认本次MCP实例ready再启动Web。正式多Web进程由管理器启动唯一MCP服务，不在AppConfig.ready中重复创建池。

## 验证和限制

验证请求隔离、一次claim、不同买家并发、到期清理、故障监督及旧请求不能重获预算，见[验收](../sdd/evidence/2026-10-29-mcp-resident/verification.md)。进程预热不保证数据库和模型均已预热；不宣称跨主机认证或操作系统级无凭据隔离。本轮没有部署或重启业务服务。
