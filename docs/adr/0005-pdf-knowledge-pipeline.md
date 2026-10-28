# 0005 PDF知识导入采用离线Worker与显式发布

Status: proposed
Date: 2026-10-26
Decision makers: dengbofu（第一阶段功能范围已在对话确认；技术记录待评审）
References: ../sdd/modules/ai-support/pdf-ingestion.md

## 背景

现有JSON导入复用现有文档/片段模型，缺少PDF/OCR、逐页恢复和页码溯源。用户明确要求实现已讨论的第一阶段。

## 方案

复用PostgreSQL/pgvector和现有Embedding/ACL，新增导入任务与页面模型；独立Docker Worker用PyMuPDF、Tesseract TSV、固定本地Tokenizer完成解析和结构切片。队列先使用PostgreSQL租约及短事务，不在Web请求内执行OCR，不新增Celery依赖。外部模型不能上传文件、发起SQL或指定知识权限。

原件/图片存受控持久目录，数据库保存结构和引用；文件必须鉴权读取。新版本以draft构建，显式确认后原子切换published版本，失败时保留旧版本服务。正文不经生成模型改写，引用保留物理页码及字符/坐标映射。

## 取舍与验证

第一阶段不实现复杂表格、多栏可靠阅读顺序和运营上传UI；对检测到的风险生成警告并要求显式确认。OCR置信度不等于事实准确性。租约采用栅栏防止失效Worker写入，重试使用已保存页和向量。新增迁移隔离PostgreSQL验证，不在业务库试跑。详细流程与命令见上述规格。
