# 有预算的混合检索：实现验证

日期：2026-10-26。模块：support_ai 0.22.0、ai_storage 0.6.0、core 0.7.1。用户要求实现前述检索改进；未授权本次提交、推送或业务库迁移。

收尾时共享工作区另有预算语义任务将support_ai总版本递增至0.23.0，本次0.22.0 changelog保留。复核本次10个实现/测试文件哈希未变；本记录不声称覆盖其他任务的完整业务验收。

## 实现范围

- 原问题/规则别名先召回，足够时0次改写；不足时同请求最多1次改写、最多2条补查；首轮与补查都使用原问题重排。
- 受控Python全文/向量通道共用可信owner及发布范围过滤；RRF、去重、比较对象预留、默认最多20个候选重排，单/多对象上下文上限3000/8000字符。
- simple全文索引和中文双字词，不称BM25；派生标题/章节搜索文本不改变引用原文或已有向量输入。数据库触发器维护批量写入、标题更新、撤回、删除及模型空间变化的epoch。
- 嵌入缓存及按数据库/ACL/知识epoch/配置分区的证据缓存；默认TTL300秒。事务内禁用证据缓存，缓存故障回源，资料缺口/服务错误不写证据缓存；数据库epoch异常不使用旧缓存。
- 已有有效结论保留，独立语义核验继续执行；增加later不得扩成餐后、茶类翻译和预测/事实的提示及保守餐后程序检查。
- 召回服务故障不冒充知识缺口；有全文证据时允许向量降级，无证据且有技术失败时返回技术错误。未部署0004时，查询探测schema_pending兼容旧向量读取，全文和证据缓存未启用。

## 实际验证

Python：E:/miniconda/envs/dadashop/python.exe，Django 3.2.12。没有调用真实付费模型。

1. `python manage.py test support_ai.test_hybrid_retrieval support_ai.test_grounding support_ai.test_cost_control --settings=support_ai.test_settings --verbosity 0`：**64项通过**，见targeted-tests.log。隔离SQLite及模拟模型，覆盖无需翻译、一次补检、无新候选不重排、候选预算和对象覆盖、年份缺口、故障后下一请求恢复、缓存副本/嵌入版本、later越界、旧schema过渡及既有证据与模型预算回归。
2. 设置PYTHONPATH包含仓库和本记录pg_settings.py.txt所示的临时配置目录后，执行 `python manage.py test ai_storage.test_hybrid_search ai_storage.tests.VectorStorageTests --settings=pg_settings --noinput --verbosity 1`：**11项通过**，见postgres-tests.log。真实本机PostgreSQL/pgvector，数据库名固定为本次专用`test_rag_hybrid_20261026`，Django自动创建并删除；业务default数据库未使用。
3. PostgreSQL涵盖全文权限、未嵌入片段、中文标题/章节、原文引用、批量更新/标题改名/撤回/删除/事务回滚、参数化输入、缓存权限分区、真实检索缓存命中与撤回即时失效、事务内禁缓存、原向量维度约束及0003→0004→0003→0004升级回退和旧schema向量读取。升级包含现存片段全文回填。
4. `python manage.py makemigrations --check --dry-run --settings=support_ai.test_settings`：No changes detected。
5. `python manage.py check --settings=support_ai.test_settings`：0 issues。
6. 10个本次实现/测试Python文件AST通过；本次跟踪文件`git diff --check`通过。源文件哈希见source-sha256.json。

复测中曾遇本机PostgreSQL连接中断/正在关闭（postgres-infra-failed.log），未重启服务；恢复后重跑成功，残留的本次专用测试库由Django清理。未把基础设施失败记为通过或修改业务库来绕过。

## 尚未执行与限制

- 没有对现有业务AI库运行0004迁移、重启常驻Worker或部署。启用混合检索需按部署流程先迁移AI库；迁移前查询仍为兼容向量通道。Worker应在schema完成后启动。
- 没有重跑100条真实模型A/B，不能把旧报告降费比例视为本次效果；不能声称实际准确率或延迟已经改善。下一轮固定源码/知识快照，明确关闭缓存或分别测冷/热缓存，以相同问题、模型和标注比较召回、nDCG、事实支持率、费用和P95。
- 覆盖依赖现有有限术语字典；其他实体、语言和复杂语义仍需要模型核验。程序规则不是任意语义蕴含证明；中文双字词不是完整分词器。
- 未进行全量仓库、浏览器、业务MySQL或并发压测；未修改商品推荐/订单业务规则及前端。
- 未提交、推送、创建PR或发布。本工作区保留原有其他任务改动；本次文件内的既有PDF入库、成本控制等实现未覆盖删除。

## 后续用户授权的启用与真实评测

上文“尚未执行”记录初次实现时的边界。随后用户明确要求应用0004并重新评测，已完成AI库备份、迁移和两组各100条真实模型评测，见[启用记录](../2026-10-26-hybrid-activation/verification.md)及[完整报告](../../../agent测试文本/2026-10-26-hybrid-100-run-03/测试报告.md)。不把后续结果冒充初次实现的测试结果。
