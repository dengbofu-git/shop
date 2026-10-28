# PDF管道启用与真实端到端验收

日期：2026-10-26（Asia/Shanghai）。用户在第一阶段实现后明确要求完成业务库迁移、常驻Worker及真实PDF端到端验收。本记录覆盖该后续授权，不代表整个RAG或其他业务能力已全量验收。

## 启用结果

- AI PostgreSQL业务库实际应用`ai_storage.0003_pdf_import_pipeline`，未修改或回退历史Migration。迁移前后既有12份知识文档、50个片段、1条长期记忆数量一致。
- 迁移前生成283969字节的私有pg_dump备份，SHA256为`30947bbd9e53205cf488ced9ed7b0b466ecb9ef25a06502a079822e022e8e1b3`。备份留在被Git忽略的本机`.scratch/pdf-activation-20261026/`，没有将备份或真实记忆内容纳入本记录。
- 在独立`pdf_restore_check_*`库实际恢复该备份，核对12/50/1行数后删除临时库；没有在业务库执行恢复或回退。
- `tea_saas-knowledge-worker-knowledge-worker-1`常驻运行，restart策略为unless-stopped，最终检查重启计数0、队列无queued/running任务。依赖镜像为第一阶段已构建镜像，代码只读挂载。
- 已重载本地`127.0.0.1:8000`Django服务，加载PDF鉴权路由与最新源码。没有修改MySQL业务表结构、订单或现有客户问答。

## 真实文档与执行范围

来源：[FAO 2014年10月CCP:TE 14/Inf.3原始PDF](https://www.fao.org/fileadmin/templates/est/meetings/IGGtea21/14-Inf3-CurrentSituation.pdf)，28页，603979字节，SHA256为`64c7d46f7f2cdbf71f1bbaf3b4526efc368c5f654639e0790446347d6c9bd508`。

在保留原件的基础上，另生成明确标记的扫描版（原文第4页，仅图片，无原生字符）和混合版（原文第1页原生文字＋第4页图片）。不是用mock代替PDF、OCR、Embedding或回答模型。检查了三类输入的预览，以及28页原件的页面总览；表格和无文字图片警告为本次私有管道验收显式确认，不证明已可靠恢复复杂表格。

使用已有活跃平台配置权限提交资料，另建独立`pdfqa*`临时买家作为私有所有者。真实Ollama bge-m3、当前DeepSeek配置（deepseek-flash，thinking enabled，revision 5）和本地Reranker参与执行，未将真实客户问答作为评测输入。

| 输入 | 页数 | Chunk/向量 | 实际方式 | 最大Token | HTTP问答 |
|---|---:|---:|---|---:|---|
| FAO原件 | 28 | 42/42 | native | 500 | 200，引用PDF第1—2页，结论verified |
| 扫描副本 | 1 | 1/1 | ocr | 382 | 200，引用PDF第1页，结论verified |
| 混合副本 | 1 | 8/8 | native＋ocr | 473 | 200，引用PDF第1页，结论verified |

还在版本切换后的混合文档上单独询问价格指数主题，确认最终来源实际包含OCR提取片段，不仅是识别到了原生文字。

## 已验证的行为

- 草稿不进入向量召回，普通买家无法下载草稿；平台权限可以预览本次草稿。
- 发布后本人可下载，原PDF SHA256匹配，页面PNG可读；未登录401、其他买家访问私有资料404，响应no-store。
- 每个Chunk都有向量；Token长度不超800。逐一验证chunk字符区间等于对应页面块字符区间，原生/OCR坐标映射保留。
- 实际HTTP问答通过知识工具、检索、生成、结论/引文校验与输出链路；响应保留文档版本、页码、映射及核验状态。
- 相同request_id重放和历史读取保持同一事实与引用；MySQL JSON会规范化坐标浮点尾数，因此仅坐标浮点比较使用1e-7绝对容差，其余字段严格一致。扫描用例记录中的0.16秒是复用已成功请求后的验收操作耗时，不是首次模型延迟，不据此报告性能提升。
- 重复提交复用同一任务；新版本草稿期间旧版本继续published；发布后原子切换，旧文件对普通买家404，新文件校验和匹配；旧版本不能覆盖新发布版本。
- 28页任务在处理完2页时执行正式cancel/retry，恢复后这2页文本块指纹未变化，最终28页、42个向量齐备，attempt=2。恢复验收任务最后保持取消的未发布草稿。
- 撤回后普通下载与检索均不再包含该验收版本。

## 验收发现与修复

1. PyMuPDF辅助函数在stdout输出提示文字，导致解析结果JSONDecodeError。修改子进程入口隔离第三方stdout，协议只输出JSON。三个初始失败任务通过正式retry入口恢复，未重置状态或伪造完成；新增2项解析协议回归测试通过。实现模块ai_storage升至0.4.1。
2. 原件首次机构名称问题返回资料不足。诊断确认正确段落已召回，但生成结论含引文没有的年份，触发UNSUPPORTED_NUMBER；安全校验没有放宽。独立诊断中的修正轮次通过；随后只询问机构名称的自然问题通过完整HTTP验收。首次保守拒答也保留为证据，不能将本次结果解释为任意问法均成功或整体RAG准确率证明。

## 数据收尾与限制

- 五份已发布验收文档均withdrawn，一份恢复验收文档保持draft/cancelled；共6份、102个验收向量保留作隔离审计，不参与正常检索。正式可检索文档/片段仍为12/50，长期记忆仍1条。
- 清除专用临时账号产生的5个咨询/5轮问答，停用该临时账号；旧Token再访问返回401。现有客户数据未作清理或批量改写。
- 本次覆盖英文FAO原件、扫描与混合副本，含一次真实中途取消/恢复。不覆盖中阿文OCR质量评测、复杂多栏/表格语义准确率、并发压测、浏览器交互或全量项目回归；第一阶段没有新增运营上传管理页面。
- 业务库迁移与本地Worker启用已完成；未提交、推送、合入PR或发布版本标签。

## 命令与证据

实际执行：`migrate ai_storage 0003 --database ai_storage`；`docker compose --env-file deploy/knowledge-worker/compose.env -f compose.knowledge-worker.yml up -d --no-build`；管理命令submit/retry/cancel/publish/withdraw；真实`/v1/support/chat/`、历史、文档和页面HTTP接口；`python -m unittest ai_storage.test_pdf_parser_protocol -v`（2项通过）；`manage.py check`。

汇总：[results.json](results.json)；执行源码指纹：[source-fingerprints.json](source-fingerprints.json)。本机详细输入、响应和日志留在`.scratch/pdf-activation-20261026/`，凭据与Token未写入证据文件。
