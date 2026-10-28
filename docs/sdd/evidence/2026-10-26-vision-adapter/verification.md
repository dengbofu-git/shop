# 可选视觉适配器初步实现验证

日期：2026-10-26。模块：ai_storage 0.5.0。当前开发分支：codex/orders-merchant-isolation。本次没有提交、推送、创建PR、部署、重启常驻Worker、配置真实视觉服务或调用付费模型。

## 实现范围

- 新增ai_storage/vision：三个严格输出合同、OpenAI兼容HTTP、独立配置快照、可选供应商参数、授权域缓存、固定错误码、重试、响应大小及页/请求预算。
- PDF CLI增加--vision-mode off/auto/force与可重复的--vision-task；默认off，不复用客服配置。解析子进程只渲染，父Worker调用视觉接口，不把AI_VISION_API_KEY传给解析子进程。
- 视觉候选保留原提取块、来源和模型标识；表格按完整行切片并重复上下文/表头，逐片校验Unicode偏移映射。
- 不确定或部分覆盖的表格阻止Embedding和发布，retry与accept-warnings不能绕过；模型返回后重新检查租约，取消后的结果不写页面。
- 无models或Migration变更。继续使用现有JSON字段、PostgreSQL/pgvector、私有文件目录及显式发布。配置、限制和操作说明见[模块说明](../../../../ai_storage/vision/README.md)。

## 实际执行

1. 本机Python3.9：`E:/miniconda/envs/<LOCAL_PROJECT>/python.exe -X utf8 -m unittest ai_storage.test_vision ai_storage.test_pdf_parser_protocol ai_storage.test_pdf_vision -q`。最终34项中30项通过，4项因本机缺少PDF Worker依赖跳过；没有将跳过项当作通过。
2. Worker镜像：`docker run --rm --name <LOCAL_PROJECT>-vision-check --network none --read-only --tmpfs /tmp:size=512m -e PYTHONPATH=/app -e AI_PDF_STORAGE_ROOT=/tmp/knowledge -v E:/django/<LOCAL_PROJECT>:/app:ro -w /app tea_saas-knowledge-worker-knowledge-worker python -m unittest ai_storage.test_vision ai_storage.test_pdf_parser_protocol ai_storage.test_pdf_vision -v`。最终34项全部通过，无跳过。容器断外网，HTTP仅访问同容器内的夹具服务器；真实执行PyMuPDF解析、表格检测与渲染，使用镜像固定BGE-M3 Tokenizer。
3. 临时数据库：`vision_adapter_test_d21888b2a34a46ebb8d89ed6`，只在该库执行`python manage.py migrate ai_storage --database ai_storage --noinput`，实际应用现有0001、0002、0003。未新增迁移，未迁移正式库。
4. PostgreSQL流程：容器显式设置AI_POSTGRES_NAME和AI_VISION_TEST_DATABASE为上述临时库、AI_POSTGRES_HOST=host.docker.internal，执行`python -m unittest ai_storage.test_vision_database -v`，3项全部通过。包含真实Worker逐页持久化、草稿退出检索、警告确认发布、原子版本切换、缓存复用、阻塞项拒绝发布/重试绕过，以及处理中取消后拒绝写入。
5. `manage.py check`无问题；13个相关Python文件AST解析、模块JSON/版本与定向空白检查通过。未运行整项目全量回归或付费问答评测。

PostgreSQL测试使用合成PDF、本机模型HTTP夹具和假Embedding向量；身份operator被替换为夹具，MySQL连接被显式禁止。因此，该结果验证存储、状态与调用边界，不代表真实模型、语义检索或身份鉴权验收。

容器镜像沿用`sha256:ad9b8bd3af3d6d5562c528370206168f8a9a04059d661a7d38a5b54558ffadf6`，代码只读挂载；不是新镜像发布。

## 清理与数据核对

临时库已删除；临时验证容器已退出；原常驻Worker仍运行，未重启。正式库前后均为12个发布文档、50个发布片段、1条长期记忆。发布知识文本/元数据指纹前后一致：`497d34d3a24251b56d163b4b8659a34132904ee9f6aac07ba21d8cda59cc6c74`。结构化记录见[results.json](results.json)。

## 尚未覆盖

没有真实视觉供应商的协议/质量/费用验收；没有证明FAO整套问答质量提升。首版表格仅有表格级坐标，未实现单元格级坐标、跨页表格恢复、人工修正UI、全量统一IR或跨进程全局配额。同步HTTP超时不等于可取消的全传输硬截止时间。模型合同通过与候选缓存命中不能替代事实审核。

默认off。后续实际启用需要配置已验证的视觉模型、让Worker加载新代码，并在独立草稿执行；业务实现授权不代表本次已部署或发布。
