# 本地 PaddleOCR 文档服务与 PDF 第一阶段

使用已验证的 Windows/WSL2、RTX 4060 8GB、PaddleOCR 3.6.0 / PaddleX 3.6.1 / PaddlePaddle GPU 3.2.1。固定镜像摘要与两份模型权重 SHA256，复用本机实验阶段的模型缓存卷。此服务只识别单页 PNG，不导入 Django、不连接数据库、不接受 URL 或磁盘路径、不决定知识权限或发布。

## 启动

先完成 GPU 自检及官方模型缓存准备。镜像用户目录是 `/home/paddleocr`，模型卷必须挂在 `/home/paddleocr/.paddlex`。

在项目根目录 PowerShell 中创建本地随机认证文件（已存在时保留）：

```powershell
New-Item -ItemType Directory -Force .scratch/paddleocr | Out-Null
python -c "from pathlib import Path; import secrets; p=Path('.scratch/paddleocr/api-key'); p.exists() or p.write_text(secrets.token_hex(32), encoding='utf8')"
docker compose --env-file deploy/knowledge-worker/compose.env -f compose.paddleocr.yml up -d
docker compose --env-file deploy/knowledge-worker/compose.env -f compose.paddleocr.yml logs --tail 30
```

如果旧实验容器仍占用 18080，先停止那个实验容器；不要移除模型卷或其他业务容器。等健康状态为 healthy 后执行：

```powershell
./deploy/paddleocr/configure-client.ps1
```

脚本从认证的 `/ready` 读取实际 revision，将私有配置写入已被忽略的 `.scratch/paddleocr/client.env`。不显示密钥，不覆盖项目 `.env`。模型 revision 包括权重、配置、软件版本与服务源码身份；服务改动后重新生成客户端配置并新建草稿，不能静默修改已有任务的版本快照。

## Worker 接入

可选 overlay 将 Worker 接入 `tea_saas-document-parser` 网络并加载本地客户端配置。默认提交仍是 legacy，不会自动给旧任务开启模型。

已有部署若使用其他资源名，可设置 `PADDLEOCR_COMPOSE_PROJECT` 与 `PADDLEOCR_NETWORK_NAME` 复用原项目及网络；两个Compose命令须使用相同的网络变量。修改配置文件不会重命名现有资源，本次交付不执行up、down或网络迁移。两个外部模型缓存卷名称保持原值。

```powershell
# 检查配置不会输出密钥
docker compose --env-file deploy/knowledge-worker/compose.env -f compose.knowledge-worker.yml -f compose.knowledge-paddleocr.yml config --quiet

# 获得对应运行环境的启用授权后，加载新代码和配置
docker compose --env-file deploy/knowledge-worker/compose.env -f compose.knowledge-worker.yml -f compose.knowledge-paddleocr.yml up -d knowledge-worker

# actor-id 必须是真实活跃且有 system_config 权限的平台操作者
docker compose --env-file deploy/knowledge-worker/compose.env -f compose.knowledge-worker.yml -f compose.knowledge-paddleocr.yml run --rm knowledge-worker python manage.py knowledge_pdf submit /input/sample.pdf --actor-id 真实ID --title "PDF资料" --source-key sample --document-backend paddleocr --document-mode auto
```

`auto` 保留简单原生文字；扫描页、缺文字图片、多栏/表格等启发式风险页使用模型。`force` 对有内容的页面使用模型。该选路不是完整的版面正确性判断，需要固定语料验收。PaddleOCR 文档后端与现有 OpenAI 兼容 `vision-mode` 在同一任务中互斥，避免重复识别与合同混用。

## 协议与运行边界

- `GET /health`：进程存活，不代表模型已就绪。
- `GET /ready`：需要 Bearer 认证，返回 ready 和固定 identity。
- `POST /layout-parsing`：需要认证；仅接受 `file`（PNG Base64）、`fileType=1`、`maxNewTokens`、`expectedRevision`。它是带项目身份校验的文档服务合同，不是 Chat Completions 接口，也不宣称完整兼容官方服务的所有参数。
- 版面分析使用 CPU，视觉识别使用 GPU。加载和推理由同一个持久 GPU 执行线程处理；模型转换后和每页结束时释放未使用的显存缓存，避免在 8GB 显卡上保留接近整卡的转换预留池。
- 模型启动后常驻；服务端一个全局 GPU 锁覆盖全部客户端。繁忙返回 429，不建立无界推理队列。HTTP 客户端断开并不终止 GPU 计算，锁会保留到实际推理结束。识别超过 300 秒时看门狗终止本服务进程，Compose 重启并释放 GPU，客户端任务失败后显式重试；已经保存的页面不重复处理。
- 图片最多 2000 万字节、800 万像素；Worker 默认渲染限制为 600 万像素。客户端响应最多 400 万字节。
- 客户端默认 300 秒读预算，不自动重放超时请求。同步 requests 的读取超时不是可以强制终止整个传输/服务计算的硬截止时间。
- 版本不符 409、未就绪 503、GPU OOM 507。OOM 后 ready=false，须检查后显式重启服务，不伪装为已恢复。
- 本服务固定原生后端版本，通过生成 ID 观察到达生成上限的区域；该检查不能证明无漏字或无幻觉。所有模型结果仍须人工审核。
- API key 只用于请求，不进入任务、缓存或日志。仅显式白名单内的内部主机允许 HTTP；客户端关闭环境代理继承及重定向。

## 页面与来源合同

使用 `page-ir-v1` 的块：稳定 ID、类型、原文、阅读顺序、PDF points bbox、提取方式、模型/配置身份和 indexable。渲染使用去旋转的完整页面，不启用裁剪/方向修正/去弯曲；以实际像素宽高分别换算 X/Y 到 PDF 坐标。原始提取块保留并退出重复索引。无模型置信度时保存 null。

原生文字的既有块坐标保持；模型正文按 block_order 组织。表格的 block_order 可以为 null，此时保留其在模型结果列表中的相对位置并要求审核，规范化 reading_order 为连续序号，源顺序另行保留。无阅读顺序的页边信息与图注保留供审核，不进入索引，不编造图示描述。原始表格 HTML 保存在 extraction.raw_text；仅矩形、完整闭合的表格转成规范化表格文字，复用现有完整行切片及表头重复。合并单元格、异常宽度、不完整表格、生成上限命中等 `document_blocking_*` 在 Embedding 前阻止任务，并且 accept-warnings 不能绕过发布检查。

普通模型警告仍进入 awaiting_review 草稿，显式发布规则保持。引用字符对应入库块文字；规范化表格不是 PDF 连续逐字原文。跨页合并、单元格坐标和运营修正 UI 属后续阶段。

## 验证

定向测试：

```text
python -m unittest ai_storage.test_paddle_document ai_storage.test_vision ai_storage.test_pdf_vision ai_storage.test_pdf_parser_protocol
```

数据库测试只允许 `AI_PADDLEOCR_TEST_DATABASE=paddle_document_test_<24位十六进制>`，实际数据库名必须完全一致，并禁止 MySQL 连接。真实识别验收及当前业务启用边界见 `docs/sdd/evidence/2026-10-28-paddleocr-stage1/verification.md`。代码实现、隔离验收、业务库启用、知识发布分别报告。
