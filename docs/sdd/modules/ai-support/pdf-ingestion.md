# PDF知识入库：第一阶段

## PaddleOCR 文档后端第一阶段（2026-10-28）

新增显式 `--document-backend paddleocr --document-mode auto|force`，默认仍为 legacy。部署、协议、统一页面块与坐标、版本身份、隔离验收和业务启用边界见 [PaddleOCR 部署说明](../../../../deploy/paddleocr/README.md) 与 [本次证据](../../evidence/2026-10-28-paddleocr-stage1/verification.md)。它独立于已有 OpenAI 兼容视觉任务，二者在同一任务内互斥。

Worker 使用独立认证 HTTP 服务，不把 GPU 模型放入受限 PDF 子进程；子进程不接收 OCR 服务密钥。服务端全局并发为 1。页面结果采用 page-ir-v1，保留原始证据、模型阅读顺序、实际渲染尺寸到去旋转 PDF points 的映射与不可变引用文本；简单原生页在 auto 下跳过 GPU。低复杂度 HTML 表格转为规范化完整行，复杂结构保留原始结果并阻止入库/发布。新增 recognizing/chunking 阶段，继续使用已有心跳、租约栅栏、取消、逐页/向量恢复和显式发布。

解析协议升级为 pdf-blocks-v3；旧未完成任务若运行版本不符应保留记录并重新提交，不能修改已冻结配置后静默重跑。第一阶段不包含跨页表格合并、单元格级定位、上传审核 UI；新路径不自动发布，也不代表全部 OCR/RAG 质量已验收。

后续可选视觉适配器的初步实现、配置及边界见[视觉适配器说明](../../../../ai_storage/vision/README.md)；默认关闭，尚未进行真实视觉模型质量验收。原有第一阶段验收结果不覆盖新增模型路径。

2026-10-26，按用户确认的第一阶段实现。范围是管理命令、独立Worker、PDF/OCR、切片、草稿检查、显式发布及RAG页码溯源，不包含运营上传页面或复杂表格还原。

## 数据与边界

- KnowledgeDocument／KnowledgeChunk／EmbeddingSpace继续存储知识、片段和向量。新增KnowledgeImportJob（任务、租约、配置、指纹、错误、审核记录）及KnowledgePage（逐页文本块、坐标、识别方式、置信度和警告），均由ai_storage路由写PostgreSQL；MySQL身份仅保存数字引用，不建跨库外键。
- 文件保存于AI_PDF_STORAGE_ROOT，默认`.scratch/knowledge-files`；Docker映射到`/knowledge`。原PDF和预览图不进入public media/static，不接受Agent构造的路径。文件名使用任务UUID，逐流校验PDF头及50MiB上限，最多200页，拒绝加密文档。
- 所有管理命令的actor-id必须是活跃平台角色且拥有system_config；这是可信服务器命令，不是客户端可任意指定身份的HTTP接口。公开资料需明确visibility=public，默认private；私有owner由活跃身份校验。
- 幂等键包括提交人、来源键、所有者、可见性、文件SHA256、标题和管道配置。同一配置重复提交复用任务；retry显式恢复失败或取消的草稿。来源键按提交人/ACL分域，不跨所有者复用文件或泄露存在性。

## 处理

1. 提交时复制原文件并建立draft及queued任务；不执行OCR或模型。PDF结构/页数检查在Worker中完成。
2. Worker通过PostgreSQL行锁、skip_locked、180秒租约和20秒心跳领取任务；所有页面/向量写入有令牌与到期检查。失效Worker不能覆盖新Worker结果。
3. 独立受限子进程使用PyMuPDF处理单页；原生文字可用时保留文字和坐标，缺文字或乱码时整页OCR，混合页对缺少可用文字的图片区域OCR。--ocr-mode force可指定全页OCR。Tesseract TSV按段落组合并保存置信度；中文、英文、阿拉伯文按提交配置选择。坐标统一为去旋转页面PDF points，rotation保留原旋转值，预览图使用同一去旋转坐标。
4. 200DPI，单次渲染最多2400万像素；OCR子调用45秒，页面子进程120秒，Linux子进程限制2GiB地址空间和120秒CPU。Worker容器另有限内存、CPU、进程数、只读根和只读代码。页面预览限制最长边1200像素。
5. 保存原生/OCR文本块、图片和警告；低置信度、表格、疑似多栏、稀疏/乱码、图片无文字均进入警告。第一阶段采用自上而下的块排序，复杂阅读顺序及表格语义需要人工对照预览，不宣称自动恢复正确。空白页不生成片段。
6. 按标题、段落、句子组织片段，识别跨多页重复的页眉页脚；使用本地固定BGE-M3 tokenizer，目标500 Token、硬上限800，尽可能保留不超过64 Token的完整句重叠。标题保留在正文或section_path中。文本不经生成模型润色，mappings保存chunk字符区间→页码/块ID/块内字符区间及bbox。偏移为Python Unicode码点，引用以入库文字为准，不保证OCR与印刷原文完全一致。
7. 每批最多8个片段调用现有Ollama适配器生成Embedding；向量空间校验模型、revision、维度，禁止混用空间。不持有长事务等待OCR/Embedding，逐页、逐批持久化；重试跳过已完成页和未变化片段的向量。
8. 全部成功后awaiting_review，文档仍draft；inspect查看警告、正文及映射，必要时通过鉴权接口下载原PDF或页面PNG。发布要求页完整、非空片段及向量齐备；有警告必须显式--accept-warnings。
9. 发布在短事务和同来源锁内撤回旧published版本并发布新版本，禁止覆盖已发布的更新版本。旧版本保留文件与片段供维护追溯，但普通检索/下载仅允许published。失败不影响旧published版本。withdraw立即退出检索，历史回答不重算。

任务：queued → running（extracting／embedding）→ awaiting_review → succeeded，异常为failed；cancel支持处理中取消，后续写入被租约栅栏拒绝。原文损坏、tokenizer或模型配置变化、解析器运行版本变化、无有效文字均明确失败，不当作空知识发布。

## 运行

新增Migration仅随源码提供；不要在未授权的业务库自动执行。依赖在独立Docker镜像中，主Web环境不需要安装PyMuPDF/Tesseract。使用空的Compose插值配置，实际凭据由Django从只读挂载的既有.env/.env.postgres读取，避免密码中美元符号及引号被Compose重解释。所有命令在项目根目录执行：

```powershell
# 构建；可用--build-arg PYTHON_IMAGE=...指定可访问的相同Python3.10基础镜像
docker compose --env-file deploy/knowledge-worker/compose.env -f compose.knowledge-worker.yml build

# 在获得业务库迁移授权之后才执行
python manage.py migrate ai_storage --database ai_storage

# 将文件放入.scratch/knowledge-input；下列示例的1必须替换为真实平台操作者ID
docker compose --env-file deploy/knowledge-worker/compose.env -f compose.knowledge-worker.yml run --rm knowledge-worker python manage.py knowledge_pdf submit /input/tea.pdf --actor-id 1 --title "茶叶资料" --source-key tea-manual --languages chi_sim+eng

# 单次消费（不需要启动长期服务）
docker compose --env-file deploy/knowledge-worker/compose.env -f compose.knowledge-worker.yml run --rm knowledge-worker python manage.py knowledge_pdf worker --once

# 或启动常驻Worker
docker compose --env-file deploy/knowledge-worker/compose.env -f compose.knowledge-worker.yml up -d
```

之后通过相同run命令执行：

```text
python manage.py knowledge_pdf inspect JOB_UUID --actor-id 1 --page 1 --chunk 0
python manage.py knowledge_pdf retry JOB_UUID --actor-id 1
python manage.py knowledge_pdf cancel JOB_UUID --actor-id 1
python manage.py knowledge_pdf publish JOB_UUID --actor-id 1
python manage.py knowledge_pdf publish JOB_UUID --actor-id 1 --accept-warnings
python manage.py knowledge_pdf withdraw JOB_UUID --actor-id 1
```

inspect是受控的人工原文预览，终端可能显示文档敏感内容；Worker日志只输出状态与固定错误码。Web进程如需读取原文件，必须将AI_PDF_STORAGE_ROOT设为同一个宿主目录。Linux挂载目录需预先给予容器UID10001读写权；任务目录0700、原件0600，Web需相同UID或显式只读ACL。输入目录只读。容器内通过host.docker.internal访问已有MySQL/PostgreSQL/Ollama，端口沿用环境配置；远程服务地址需修改Compose环境映射。

tokenizer固定下载BAAI/bge-m3修订5617a9f61b028005a4858fdac845db406aefb181的tokenizer.json，仅在镜像构建时联网；任务保存其SHA256，执行时校验。页面解析实际PyMuPDF和Tesseract版本保存于文档metadata，重试不允许静默更换运行版本。

## 检索和引用

search_knowledge仍先限定published、同EmbeddingSpace及public/本人private，不扩大ACL。检索DTO增加document_version；claim_sources及grounding.sources为PDF附加文档ID、片段ID、页码、版本、提取方式和位置映射，普通JSON来源保持兼容。引用文字显示页码与版本；quote校验对应已入库文字，不能证明OCR识别正确。

- `GET /v1/support/knowledge/documents/<UUID>/file`
- `GET /v1/support/knowledge/documents/<UUID>/pages/<页码>`

均要求Bearer身份。活跃平台system_config可查看草稿；活跃买家只能读已发布的公开或本人私有资料，不可见与不存在均404。文件下载不接受路径或Token查询参数。现有客服来源列表对同源固定PDF路径使用带Authorization的fetch下载，禁止重定向并在请求/接收后复查账号；外部HTTPS资料保持原跳转方式。裸链接没有Bearer会返回401。

## 验证边界

新增0003在临时隔离PostgreSQL库实际执行升级、回退和再升级，完成后删除临时库；没有迁移业务库。未新增或运行自动化测试、真实知识入库/模型评测，不把语法或配置检查当作OCR质量与端到端验收。构建和检查的最终结果应随本次交付说明记录。

### 2026-10-26本次检查结果

- 本机`manage.py check`、`makemigrations ai_storage --check --dry-run`、新增Python AST、JSON解析、客服模板加载与`node --check client/static/js/buyer-support.js`通过；无自动化测试执行。
- 隔离库`pdf_migration_check_c8acd1f44324431c`完成0001→0003、0003→0002、0002→0003，随后删除临时库；没有使用业务库验证迁移。
- `docker compose --env-file deploy/knowledge-worker/compose.env -f compose.knowledge-worker.yml config --quiet`通过。
- 默认Docker镜像代理403、Debian HTTP下载502；使用公开同版本基础镜像并切换Debian HTTPS及有限重试后成功构建。实际命令：`docker build --build-arg PYTHON_IMAGE=public.ecr.aws/docker/library/python:3.10-slim-bookworm -f deploy/knowledge-worker/Dockerfile -t tea_saas-knowledge-worker-knowledge-worker .`。
- 镜像指纹`sha256:ad9b8bd3af3d6d5562c528370206168f8a9a04059d661a7d38a5b54558ffadf6`；源码运行时只读挂载，不打包凭据。容器`--network none --read-only`执行Django检查和knowledge_pdf --help通过。
- 容器确认PyMuPDF1.26.7、tokenizers0.21.4、本地固定Tokenizer可加载，Tesseract安装ara/chi_sim/eng/osd语言数据。未处理样本PDF、执行OCR质量或多轮RAG业务验收、调用真实Embedding或回答模型。
- 未启动常驻Worker，未执行业务库Migration，未提交、推送或部署；现有工作区其他改动保留。

### 后续启用与真实验收（2026-10-26）

用户随后明确授权完成上述未执行项。现已备份并验证恢复AI存储库、实际应用0003、启动常驻Worker，完成FAO原版28页、扫描页和混合页的真实OCR/Embedding/HTTP问答及权限、引用、版本切换、重试和断点恢复验收。新增解析协议修复及2项回归测试通过，ai_storage为0.4.1。已撤回或隔离验收资料、清除临时咨询并停用临时账号；原有正式知识与记忆数量保持。

上述“未迁移/未验收”是第一阶段实现时的历史状态，当前以[启用和验收记录](../../evidence/2026-10-26-pdf-activation/verification.md)为准。保留实际的首次保守拒答和覆盖限制，不据此声称完整RAG质量已通过评测。
