# 可选视觉适配器：初步实现

本模块由离线PDF Worker调用，不是问答Agent工具，也不提供数据库连接、SQL、上传路径或发布能力。默认关闭；不复用客服的`SUPPORT_*`配置。

## 配置与启用

配置项见[配置模板](../../deploy/knowledge-worker/vision.env.example)。将需要的项追加到现有本地`.env`，不要覆盖原文件或提交凭据。`BASE_URL`为包含版本前缀的基础地址，例如`https://供应商地址/v1`，适配器仅追加`/chat/completions`。只允许HTTPS，回环地址可使用HTTP进行本机验证；不跟随重定向。

确认选定模型支持图片输入后，按该供应商实际能力配置：

- `OUTPUT_FORMAT`：`json_object`或`json_schema`。后者发送严格Schema；所有结果仍做本地Pydantic合同校验。
- `TOKEN_PARAMETER`：`max_tokens`或`max_completion_tokens`。
- `IMAGE_DETAIL`：`omit`、`auto`、`high`、`low`。
- `THINKING`：默认`omit`，确需供应商扩展时才设置`disabled`、`enabled`、`auto`。
- `TEMPERATURE`：默认`omit`，也可按支持情况设置0～2的有限数值。
- `REVISION`：记录供应商可固定的模型修订；别名没有不可变版本时如实记录，不能保证未来重跑一致。

模型配置与协议、提示词、输出合同版本在提交任务时冻结，但不保存API Key。运行配置变化时旧任务失败关闭，应按新配置新建草稿任务；密钥本身可轮换。未开启视觉的旧任务不要求视觉配置。

以下管理命令在新代码的Worker进程中执行；现有常驻Worker需要另行重启才会加载新代码。本次实现没有配置真实模型或重启服务。

```powershell
# 默认为 off，保持原生提取及本地Tesseract路径
python manage.py knowledge_pdf submit sample.pdf --actor-id 1 --title "样本" --source-key sample

# actor-id须替换为真实的活跃平台操作者；仍默认private
# auto只处理已选任务对应的页面风险
python manage.py knowledge_pdf submit sample.pdf --actor-id 1 --title "样本" --source-key sample --vision-mode auto

# 指定只执行表格提取；force不自动执行其他任务
python manage.py knowledge_pdf submit sample.pdf --actor-id 1 --title "表格样本" --source-key sample --vision-mode force --vision-task table_extract

# 同一任务可重复传入--vision-task；force未指定任务时仅ocr_text
# 在包含PyMuPDF/Tesseract/固定Tokenizer的Worker环境处理
python manage.py knowledge_pdf worker --once --job-id JOB_UUID
```

容器执行沿用[PDF入库说明](../../docs/sdd/modules/ai-support/pdf-ingestion.md)的只读挂载和空Compose插值文件，不通过Compose重新解释本地密钥。不要在旧Worker仍消费队列时误以为新视觉路径已启用。

## 模块与合同

- `config.py`：配置验证、无密钥快照、任务模式与配置漂移检查。
- `contracts.py`：三类严格输出合同，拒绝额外字段、非有限数字、重复JSON键、错误表宽和非法坐标。
- `openai_compatible.py`：Base64图片、Chat Completions请求、可选供应商参数、响应大小限制、错误分类和有限重试。
- `cache.py`：经过合同校验的候选结果缓存；包含授权域、图片、任务、上下文、配置和版本身份，原子保留首个结果。
- `pipeline.py`：模型候选转换为PDF页面块，保留原始提取结果和定位、提取方式、模型版本及缓存摘要。

任务包括`ocr_text`、`table_extract`、`figure_describe`。OCR和图示返回相对实际上传图片的归一化bbox；表格返回表格级bbox、标题、单位、列头、等宽行、脚注及不确定单元格。原语言、数值和年份不主动翻译或补齐。自报confidence可以为null，不作为事实核验分数，也不混入Tesseract的词置信度。

## Worker集成与边界

解析子进程只渲染受限图片并返回候选任务，不发送模型请求；子进程环境移除`AI_VISION_API_KEY`。图片按现有200DPI和2400万像素上限生成，仅在当前任务私有目录暂存，用后清理。模型输入另外受字节上限限制。

auto模式按现有检测结果选路：表格警告触发table_extract；低OCR置信度、稀疏/乱码、多栏或图片无文字触发ocr_text；面积占比至少3%的图片，或符合数量/面积规则的矢量图触发figure_describe。它是启发式路由，不保证覆盖所有表格和图示。force只执行显式任务，空白页跳过。

每次Worker领取的视觉处理最多20页、40次供应商请求（默认值），重试也消耗请求额度；缓存命中不消耗请求额度。并发上限按当前进程生效，多Worker部署的总配额尚未实现。HTTP连接/读取超时、信号量准入、重试和分块读取均有时间预算检查，但同步requests不是可强制取消的整个传输硬截止时间，不宣称慢速流场景严格90秒结束。

OCR替换用于索引的正文时，旧来源块保留为`indexable=false`。表格完全覆盖的旧块也保留但退出索引；遇到粗粒度块部分横跨表格与正文，不静默删除内容，而记录阻塞问题。视觉描述单独成块。所有视觉结果添加人工审核警告，文档仍为draft。

视觉表格按完整行分片、重复标题/单位/脚注和表头，最大沿用800个BGE Token；单行或表头无法安全容纳时明确失败。映射指向存储的规范化表格文字，不表示PDF原件存在完全相同的连续字符串。字符偏移仍为Unicode码点。常规非视觉正文策略本轮没有整体替换成按页切片。

模型拒答、截断、无效JSON、错误合同、认证失败均不当作成功结果。只有429和部分5xx、连接/读取超时有限重试；不自动删除不支持的参数重发。缓存不包含密钥、请求头或隐藏推理，只保留合同候选与选定用量字段。合法但不确定的候选可缓存用于审查，仍然阻止发布，不能把缓存命中当成质量通过。

`vision_blocking_*`会在Embedding之前令任务以`VISION_REVIEW_REQUIRED`失败，页记录与问题保留。`retry`会继续检查这些页，不会悄悄绕过；`publish --accept-warnings`也不能绕过阻塞项。首版尚无修正页面编辑器，需要检查原件后调整输入/策略并新建草稿。一般人工审核警告沿用显式发布机制。

模型等待不持有数据库事务，返回后重新检查租约；处理中取消不会写入过期页面。旧发布版本继续提供检索，只有显式发布成功才事务切换版本。

## 当前范围与验证

已实现：可插拔接口、三个任务合同、独立配置、可选Worker路径、私有候选缓存、表格行切片与来源映射。使用现有JSON字段，不新增Migration。parser/chunker分别升级为`pdf-blocks-v2`、`structure-token-v2`；已记录旧解析运行时的未完成任务可能因版本冻结检查而失败，应保留旧记录并重新提交，不在原任务中静默更换运行版本。

未实现：逐单元格坐标、二维表格正确性自动核验、跨页表格合并、运营配置/修正页面，以及全量统一IR迁移。未选择真实供应商或验证付费模型质量。结构正确不等于提取事实正确，不能直接视作先前FAO表格评测的质量修复已验收。

验证证据见[2026-10-26初步实现](../../docs/sdd/evidence/2026-10-26-vision-adapter/verification.md)。
