# 0001 统一运行日志与请求关联

Status: accepted
Date: 2026-10-19
Decision makers: 项目用户（本聊天授权）
References: 用户审阅日志四阶段改进方案后回复“实施”；本轮实施方案建议的前两阶段，见 [SDD](../sdd/modules/platform/runtime-logging.md)
Supersedes: none
Superseded by: none

## 背景与问题

已有 Python logging、用户模块 print、AgentSpan 及 OTel 链路，但缺少统一输出和全站请求关联。部分日志会直接带入账号、手机号、验证码、请求正文或原始异常。现有 Python 3.9、Django 3.2 与 OTel 运行环境继续使用，不新增日志服务器或数据库表。

## 决定与取舍

使用标准 logging 配置、正向字段 JSON／文本格式化器、受限固定事件、同步请求中间件和 ContextVar。默认控制台输出，本地单进程可开启轮转文件；日志写入失败隔离于业务流程。普通消息与参数一律不输出，换取第三方任意内容不会通过消息模板进入日志；诊断依赖事件、模块、异常类型、栈位置和关联编号。Python warnings 纳入同一边界。

HTTP 编号由服务器生成，与 Agent 幂等 ID 分离；真实当前执行的 OTel Trace 可以关联运行日志，历史响应中的 Trace 不自动继承。异常只保留不含正文的栈结构，Django 框架异常继续负责未处理异常记录。

本阶段不采用逐条数据库写入、远程同步日志导出或应用内共享多进程文件轮转；控制台交由部署端采集，后续持久化与检索另行决定。同步日志仍有格式化和输出开销，不承诺零阻塞或可靠审计；需要高吞吐时再依据实际测量设计有界队列。

## 影响与验证

涉及 core、users、orders、support_ai；不修改数据库模式、身份授权、会话幂等和响应 JSON。增加响应头 X-Request-ID。现有命令／外部进程的直接 stdout 不被全局截获。

覆盖隐私、单次异常、并发隔离、ASGI、文件失效、轮转、真实视图替身及 OTel 根／子 Span 关联，结果见[验证记录](../sdd/evidence/2026-10-19-runtime-logging/verification.md)。本 ADR 记录用户已授权的实现选择，不代表代码已提交、上线或后续审计／告警方案已获批准。
