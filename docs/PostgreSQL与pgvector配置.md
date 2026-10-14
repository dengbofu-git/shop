# PostgreSQL 长期记忆与 pgvector 知识库

当前分工：MySQL 保存用户、商品、订单，以及客服会话与短期上下文；PostgreSQL 的普通 JSONB 表保存长期偏好，知识文档与片段保存在同库，向量字段使用 pgvector。Agent 图仍只消费 DTO，不直接查询任何数据库。

## 本地 Docker

Compose：`compose.ai-storage.yml`。镜像固定为 `pgvector/pgvector:0.8.7-pg16-bookworm`，发布本机 `127.0.0.1:5433`，持久化到项目专属 `dadashop-ai-storage_postgres_data` 卷，启用健康检查和 `unless-stopped` 重启策略。已有 MySQL、Redis 等容器不属于该 Compose。

凭据在被 Git 忽略的 `.env.postgres`；示例是 `.env.postgres.example`。Django 先加载 `.env` 再加载 `.env.postgres`，进程环境变量优先。首次配置生成随机密码，不把密码写入 Compose、SQL 或文档。该镜像中的 POSTGRES_USER 具备本地初始化/迁移权限；这是开发栈凭据，不作为生产最小权限方案。

```powershell
docker compose --env-file .env.postgres -f compose.ai-storage.yml up -d --wait
python manage.py migrate ai_storage --database ai_storage
docker compose --env-file .env.postgres -f compose.ai-storage.yml ps
```

首次初始化 SQL 和 Django 迁移都会确保 vector 扩展存在。已有卷更换环境变量不会自动更换库内密码。停止服务可用 `docker compose --env-file .env.postgres -f compose.ai-storage.yml stop`；重启沿用已有卷。不要用 `down -v` 作为普通停止命令。

## 数据库路由与长期记忆

数据库别名 `default` 为 MySQL，`ai_storage` 为 PostgreSQL。`AiStorageRouter` 将 `ai_storage` App 的读写和迁移限定到 PostgreSQL，并拒绝与 MySQL 模型建立跨库关系。

`BuyerMemory.owner_id` 保存 MySQL UserProfile 的逻辑 ID，没有跨数据库外键。服务端先通过 MySQL 验证用户，再以其 ID 访问 PostgreSQL 偏好。长期记忆读写接口已使用 BuyerMemory，不会在 PostgreSQL 故障时回退到 MySQL；失败返回 503。

普通账号删除不会通过跨库 FK 自动清理这张表；账号生命周期需要应用层清理/补偿机制。数据搬迁或恢复时也必须保持用户 ID 的对应关系，不得随意重用 ID。没有跨 MySQL/PostgreSQL 原子事务的承诺。

上一版 `support_ai.SupportPreference` MySQL 表只保留作为迁移来源。迁移命令验证旧数据并拷贝，不覆盖已有 PostgreSQL 偏好，不删除旧行；重复运行安全：

```powershell
python manage.py transfer_support_preferences
```

MySQL 连接由 `.env` 的 DB_* 配置决定；登录失败时先修正该配置。该命令不会创建 MySQL 业务库或重置账号密码。

## 知识与向量空间

- `KnowledgeDocument`：来源键、版本、标题、来源引用、draft/published/withdrawn、public/private、所属用户与 JSON 元数据。
- `KnowledgeChunk`：文档内序号、原文、位置元数据、可选 vector 和所属 EmbeddingSpace。只有需要向量检索的知识片段才保存向量；明确分类/品牌偏好仍按用户 ID 精确读取。
- `EmbeddingSpace`：provider/model/revision/dimensions 组成稳定空间身份。查询只比较同一空间的向量；已存片段后空间不可修改，换模型建立新空间并重新向量化。

目前没有选定实际 Embedding 模型，因此使用 `vector` 不固定全局维度。数据库触发器检查每个向量与其空间的维度一致且非零；向量与空间必须同时有值或同时为空。先采用精确余弦距离检索；确认模型与规模后，再为固定维度和空间增加 HNSW 表达式/部分索引，不盲目固定成 1536 维。

`ai_storage.knowledge.search_knowledge()` 是应用层检索基础函数：只查询已发布、当前用户可见的公开或本人私有知识，在同模型空间按距离排序，验证输入向量并限制返回数量。它不开放给模型作为数据库工具。

本次建立存储与检索基础能力，未实现文件解析、切分、真实 Embedding 调用、知识上传管理或客服问答 RAG 接入；测试的合成向量仅证明数据库功能，不代表语义检索质量。

## 检查

```powershell
# 全部内存 SQLite，向量 SQL 测试明确跳过
python manage.py test support_ai ai_storage --settings=support_ai.test_settings --noinput
# 业务数据用 SQLite，AI 数据使用独立 test_dadashop_ai PostgreSQL 测试库
python manage.py test support_ai ai_storage --settings=support_ai.pg_test_settings --noinput
python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings
```

真实 PostgreSQL 测试覆盖记忆读写、归属、旧偏好迁移幂等、公开/私有知识过滤、撤回、模型空间隔离、维度校验与零向量拒绝。测试库与业务 PostgreSQL 数据库不同。

设计依据：[pgvector 官方说明](https://github.com/pgvector/pgvector)、[pgvector Python/Django 集成](https://github.com/pgvector/pgvector-python)、[Django 多数据库边界](https://docs.djangoproject.com/en/3.2/topics/db/multi-db/)。
