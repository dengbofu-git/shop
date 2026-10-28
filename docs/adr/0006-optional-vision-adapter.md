# 0006 PDF导入增加可选OpenAI兼容视觉适配层

Status: proposed
Date: 2026-10-26
Decision makers: dengbofu（已要求初步实现，完整迁移架构仍待评审）
References: 0005-pdf-knowledge-pipeline.md; ../sdd/modules/ai-support/pdf-ingestion.md

## 背景与方案

前次同源评测发现OCR数字保留不能证明表格行列关联正确。用户要求借鉴Store的OpenAI兼容视觉接口，并明确要求初步实现。

复用PostgreSQL/pgvector、现有离线Worker、租约和显式发布，不引入Store的Qdrant或MQ拓扑。模型适配层不接触数据库；使用独立AI_VISION配置，任务按off/auto/force显式选择，默认off。保留三类输出合同：原语言OCR、结构化表格、派生图示描述。能力配置显式处理Schema、输出预算字段和供应商扩展，不假定所有兼容服务支持相同参数。

## 对0005第一阶段边界的补充

仅显式视觉任务允许产生模型提取/描述候选；原始来源块保留。规范化表格和视觉描述不冒充PDF连续原文，引用对应存储片段并保留提取方式与来源定位。常规off路径仍不使用生成模型改写正文。

合法JSON与coverage不代表语义正确。歧义表格阻止Embedding和发布，一般视觉输出必须人工审核。首版不自动恢复全部二维关系，也不包含统一IR与运营修正UI。

## 验证及后续

仅使用本机HTTP模型夹具、合成PDF和临时PostgreSQL做验证；未调用付费模型、迁移正式库或部署。后续应在选定供应商后对固定公开语料执行结构、事实、成本和完整问答评测，不能把协议测试通过当作视觉质量通过。证据见../sdd/evidence/2026-10-26-vision-adapter/verification.md。
