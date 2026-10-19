# tea_saas 工程命名

更新：2026-10-19。用户要求统一仓库中的产品文本、文件名和变量；本次为本地实现，尚未提交或发布。

## 有效约定

- 三语产品显示名均为 `tea_saas`。Django 工程包为 `tea_saas`，入口使用 `tea_saas.settings`、`tea_saas.urls`、`tea_saas.wsgi`、`tea_saas.asgi`。
- 原工程前缀的 Python 常量和环境变量采用 `TEA_SAAS_`；图片响应读取 `settings.TEA_SAAS_MEDIA`。
- 前端对象、事件命名空间和登录存储统一采用 `tea_saas` 前缀。登录令牌仍仅存放于当前标签页；旧存储键不会自动继承，刷新后需重新登录。
- MCP 目录为 `tools/tea_saas_mcp`，服务名为 `tea_saas-catalog`，宿主需配置实际存在的 `TEA_SAAS_PYTHON`。用户级 MCP 注册需按[接入说明](../../../MCP与Skill接入.md)更新并重新加载，本次未修改用户级配置。
- 仓库 Skill 使用符合格式要求的 `tea-saas-change-delivery` 名称，位于 `.agents/skills/tea-saas-change-delivery`。

## 外部资源兼容

工程包改名不移动当前物理工作区，不重建 Conda 环境，不修改真实数据库名、数据库账号、现有用户邮箱、Docker 卷或 Git 历史。新安装示例使用新名称；已有安装通过本地私有配置继续引用实际资源。二进制图片内容、依赖和生成缓存不属于源码文本替换范围。

`DB_NAME`、`AI_POSTGRES_NAME`、`AI_POSTGRES_USER` 继续以现有私有环境配置为准。四类持久卷可通过 `AI_POSTGRES_VOLUME_NAME`、`AI_OLLAMA_VOLUME_NAME`、`AI_RERANK_VOLUME_NAME`、`AGENT_PROMETHEUS_VOLUME_NAME` 指定；本机已绑定现有卷，未创建或删除数据卷。已有容器的 Compose 标签与项目归属不自动迁移，重新编排前需单独制定迁移步骤，不能只修改卷名后运行另一套服务。

虚拟商品写入命令和两份历史评测脚本要求传入 `--expected-database-name`，并保留服务器 UUID 校验。参数必须来自人工确认的目标，不能仅因项目改名假定业务库也已改名。本轮未执行写数据命令、迁移或模型评测。

## 历史资料

命名实现阶段曾修改 `users/migrations/0006_create_admin_user.py`、`0007_create_customs_user.py` 的两处默认邮箱文本。2026-10-19 交付门禁实际阻止历史迁移修改后，用户明确授权备份并恢复这两份迁移原文，其余改动继续交付。因此历史迁移保留原始默认邮箱，不要求其符合当前产品命名；没有执行数据库操作或绕过 Hook。已有名称扫描回归尚未为此历史边界调整，不能继续沿用此前“全文件旧名称零残留”的结论。

历史报告和源码快照中的旧名称也已规范化。因此历史记录内的原始 SHA／文件摘要只描述当时原件，不能再用于验证规范化后的文本。名称替换前后摘要见[规范化清单](../../evidence/2026-10-19-project-rename/normalization-manifest.json)，后续修订有单独当前摘要；这不是重新执行历史评测的证据。

## 验证与边界

当前命名检查覆盖 Git 已跟踪和非忽略的未跟踪文件名及 UTF-8 文本，不扫描 `.git`、私有环境、依赖、缓存和二进制图片。入口、模块归属、前端契约、隔离业务测试及 MCP 调用链分别验证。实际结果和本地运行限制见[本轮验证记录](../../evidence/2026-10-19-project-rename/verification.md)。
