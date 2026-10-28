# 0008 PDF 导入增加独立的本地 PaddleOCR 文档后端

Status: proposed
Date: 2026-10-28
References: 0005-pdf-knowledge-pipeline.md; 0006-optional-vision-adapter.md

## 背景

用户要求实施已讨论的第一阶段：本地服务化、适配器、统一页面结构和坐标、Worker 接入、小 PDF 到草稿入库。此前 RTX 4060 8GB 的官方报纸图片两轮识别已通过，但不代表真实 PDF 端到端通过。

## 方案

独立 PaddleOCR 文档后端不伪装成 Chat Completions；现有 OpenAI 兼容视觉任务保留。由可信 Worker 调用只接收单页 PNG 的认证 HTTP 服务，模型不连接数据库、不控制文件路径或知识权限。使用现有 PostgreSQL 任务租约、页面、JSON 字段、切块、Embedding 和显式发布，无新增数据库迁移。

服务固定镜像、模型权重及软件版本，以内容身份冻结任务配置；全局单 GPU 请求，超时不自动重放。不同 HTTP 线程显式建立 Paddle 动态图/GPU 上下文，防止脚本路径通过但服务路径失败。

page-ir-v1 保存来源块、顺序、提取方式和去旋转 PDF points 坐标。模型覆盖区域的旧块保留但退出索引。仅矩形完整表格转换为规范化文字；合并单元格、结构异常、生成上限命中等阻止向量化及发布。普通候选进入人工审核草稿。

## 取舍

首版以单页 HTTP 和同步等待复用 Worker，页面处理不持有数据库事务；并不声称请求断开能取消 GPU 计算，OOM 后显式重启。auto 使用已有启发式选路，不宣称复杂阅读顺序、跨页表格、单元格定位和人工修正 UI 已完成。

## 验证与启用

实际协议、隔离 PostgreSQL、真实本地 OCR/Embedding 结果见 ../sdd/evidence/2026-10-28-paddleocr-stage1/verification.md。业务 MySQL 连接检查被自动审批拒绝；未用其他路径绕过。对应业务身份验收和业务 Worker 启用与隔离验证分别报告。
