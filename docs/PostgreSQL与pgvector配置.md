# PostgreSQL 统一存储与 pgvector 知识库

2026-11-02起代码采用单一PostgreSQL/default连接，覆盖用户、商品、交易、库存、客服会话、偏好和知识。Redis与文件存储保持。实际切换状态、保留来源库和验收以[统一数据库规格](sdd/architecture/postgresql-unification.md)及其证据为准；旧日期材料中的双库说明不再是新运行配置。

## 新环境配置

从`.env.example`填写POSTGRES_HOST/PORT/NAME/USER/PASSWORD，模式为unified。基础设施参考`.env.postgres.example`与compose.ai-storage.yml；Compose保留原卷名时，已有数据库/用户/密码不会因环境变量改变而自动修改。不能把空库初始化当作已有数据迁移。

```powershell
docker compose --env-file .env.postgres -f compose.ai-storage.yml up -d --wait
python manage.py migrate
python manage.py import_middle_east_tea_knowledge
```

首次使用需要创建配置所指的数据库、安装pgvector并授予必要迁移权限。运行用户与生产最小权限应单独设计；不要把本地初始化超级用户等同生产方案。Django同一default连接可跨App事务，OCR/embedding及模型调用继续在事务外。

AI App使用ai_storage.database.alias()，统一模式返回default；不注册第二个ai_storage连接。BuyerMemory.owner_id暂保留逻辑引用，不因同库自动新增外键或账号删除级联；迁移必须保留用户ID。

## 已有两库迁移

仅操作员显式legacy模式读取旧DB_*和AI_POSTGRES_*，源驱动在tools/database-transfer-requirements.txt。正式应用依赖不包含MySQL驱动。tools/database_transfer.py提供新目标准备、只读导出、token/基线保护的导入及逐表核验；操作顺序及回退限制见[迁移规格](sdd/architecture/postgresql-unification.md)。不直接把MySQL SQL dump导入PG，不合并旧迁移记录冒充建表完成。

来源备份、归档、本地环境文件和令牌均含敏感内容，不入Git。保留原库供恢复；新库接收写入后不得仅切换配置回旧库。原生PG备份必须在另一空库实际恢复验证。

旧SupportPreference表仅作为历史偏好来源保留，transfer_support_preferences不会覆盖现有BuyerMemory或删除旧行；新读写通过确认过的现有偏好API，三层记忆新功能不在本次迁移范围。

## 知识与向量空间

- `KnowledgeDocument`：来源键、版本、标题、来源引用、draft/published/withdrawn、public/private、所属用户与 JSON 元数据。
- `KnowledgeChunk`：文档内序号、原文、位置元数据、可选 vector 和所属 EmbeddingSpace。只有需要向量检索的知识片段才保存向量；明确分类/品牌偏好仍按用户 ID 精确读取。
- `EmbeddingSpace`：provider/model/revision/dimensions 组成稳定空间身份。查询只比较同一空间的向量；已存片段后空间不可修改，换模型建立新空间并重新向量化。

当前默认 BGE-M3 使用1024维，`vector`仍不固定全局维度，以EmbeddingSpace校验具体模型空间。数据库触发器检查每个向量与其空间的维度一致且非零；向量与空间必须同时有值或同时为空。先采用精确余弦距离检索；确认模型与规模后，再为固定维度和空间增加 HNSW 表达式/部分索引，不盲目固定成 1536 维。

`ai_storage.knowledge.search_knowledge()` 是应用层检索基础函数：只查询已发布、当前用户可见的公开或本人私有知识，在同模型空间按距离排序，验证输入向量并限制返回数量。它不开放给模型作为数据库工具。

当前首批语料位于 `ai_storage/data/middle_east_tea.json`。包含 WITS/UN Comtrade 2023 HS 0902 进口值/数量（可用时）和有明确标注的 FAO 2014 黑茶消费历史估计/2023 预测，以及 UNESCO、沙特百科、约旦佩特拉通讯社、Go Türkiye 和学术论文的茶文化/生产摘要。贸易进口不代表消费；FAO 的 2023 数值是旧报告预测而非实测。数据是有来源的可扩充起始语料，后续可以继续补国家统计、法规、茶类偏好、供应来源和更新年份。客服问答仅使用已发布且当前用户可见的检索结果，并返回命中的来源标题和 URL；未知商品事实和商城政策仍需走人工客服。

## 检查

```powershell
# 最终统一数据库验收：只允许显式指定临时PG端口/凭据和独立Redis
# TEA_SAAS_PG_TEST_PORT、TEA_SAAS_PG_TEST_PASSWORD、CART_TEST_REDIS_URL须指向隔离资源
python manage.py test orders inventory pays carts goods supplier engagement users support_ai ai_storage logistics --settings=tea_saas.pg_test_settings --noinput
# 全部内存 SQLite，向量 SQL 测试明确跳过
python manage.py test support_ai ai_storage --settings=support_ai.test_settings --noinput
# 业务数据用 SQLite，AI 数据使用独立 test_tea_saas_ai PostgreSQL 测试库
python manage.py test support_ai ai_storage --settings=support_ai.pg_test_settings --noinput
python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings
```

真实 PostgreSQL 测试覆盖记忆读写、归属、旧偏好迁移幂等、公开/私有知识过滤、撤回、模型空间隔离、维度校验与零向量拒绝。测试库与业务 PostgreSQL 数据库不同。

设计依据：[pgvector 官方说明](https://github.com/pgvector/pgvector)、[pgvector Python/Django 集成](https://github.com/pgvector/pgvector-python)、[Django 多数据库边界](https://docs.djangoproject.com/en/5.2/topics/db/multi-db/)。
