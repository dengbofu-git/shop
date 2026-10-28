# 最新工作区整合交付

日期：2026-10-28（Asia/Shanghai）。用户授权重新核对本地工作区，并提交、推送全部最新工作、创建面向main的MR；未授权合入、生产部署或业务库迁移。

## 范围与整合

- 起始分支codex/orders-merchant-isolation，起始HEAD为25a08ee29e23ce1bd479951e5860b44c9dfb2a89；完整本地快照提交97a6582，正常合并主干提交9880e55。源工作树的其他历史改动保留，未stash、reset或强删。
- 同步主干a0747157b45e862e0f1caa524978776d2fad7acd。全部10个登记工作树已盘点，各自HEAD均已在主干；pr8-ci的38项旧改动与此前整合记录逐文件哈希一致，适用的商家隔离、状态筛选及试单／预售保护已由主干保留，未用旧直接下单／支付链路覆盖新链路。
- 另一工作树的最新README改写纳入当前分支，并按现有源码同步混合检索、证据核验、自动数量和PDF边界。原工作树保持原状。
- 76处文件重叠逐项记录取舍：主干的交易、权限、履约修复和回归覆盖保留；本地较新的Agent多轮预算、可变件数、方案同步、订单定位、模型预算、混合检索、PDF/OCR与可选PaddleOCR管线保留；版本不倒退，changelog保留双方条目。历史证据优先保留已发布主干版本，另一版本仍可从快照提交恢复。
- 仅为正常合并同步旧测试契约：客户端模拟DOM支持订单片段；模型替身指向当前客户端类并禁止真实生成；技术提取失败不查询商品、不保存轮次；组合穷举同时校验1—4款普通／接近两种排序。没有为通过测试改写生产业务逻辑。
- 交付整理只规范测试文本行尾／末尾空白，原始文本在任务目录备份；PDF与证据补丁按二进制类型保存原字节。所有Git Hook正常执行。

模块版本：core0.8.3、support_ai0.23.2、ai_storage0.7.0、web0.31.9、orders0.4.3、supplier0.4.2；其余模块保留已同步的最高版本。

## 实际验证

使用E:/miniconda/envs/dadashop/python.exe与E:/New Folder/node.exe。命令及逐项结果见[validation.json](validation.json)，测试日志位于本目录。

| 验证 | 实际结果 |
| --- | --- |
| manage.py check --settings=support_ai.test_settings | 无问题 |
| manage.py makemigrations --check --dry-run --settings=support_ai.test_settings | No changes detected |
| manage.py test orders inventory pays carts goods supplier engagement users support_ai --settings=support_ai.test_settings --noinput -v 1 | 470项，14项跳过，其余通过；SQLite隔离库，模型替身 |
| manage.py test orders.test_reservations orders.test_reservation_contracts pays.test_reservation_signatures supplier.test_order_actions engagement users.test_nickname inventory --settings=engagement.test_mysql_settings --noinput -v 1 | 121项通过；随机test_engagement_* MySQL隔离库，运行后删除 |
| manage.py test ai_storage.test_hybrid_search ai_storage.tests.VectorStorageTests --settings=pg_settings --noinput -v 1 | 11项通过；随机test_delivery_ai_* PostgreSQL/pgvector隔离库，运行后删除 |
| python -m unittest ai_storage.test_paddle_document ai_storage.test_vision ai_storage.test_pdf_vision ai_storage.test_pdf_parser_protocol | 58项，4项跳过，其余通过；本地合成HTTP／模型替身，未调用真实OCR模型 |
| node --test client/tests/*.test.js（逐文件执行） | 24个文件、92项测试通过 |
| 受影响模板编译／渲染及静态解析 | 2个模板、2个页面、21个静态资源通过 |
| tools/git_policy.py verify --base origin/main（9880e55） | 321个变更文件、16个模块、85份Python/JS语法检查通过 |
| tools/module_versions.py check；git diff --check | 通过；完整迁移目录无重复编号，历史迁移未改写 |

新增数据库交付仅ai_storage的0003、0004；其他本地迁移已与主干一致。PostgreSQL隔离测试实际应用迁移并验证混合搜索、权限和升级／回退行为。未对业务库运行迁移或回退。

首轮测试遇到沙箱临时目录清理、回环HTTP限制和过时模型替身／断言；更换任务专用临时目录、使用本地合成HTTP夹具并按现行契约校正后复测。首轮失败记录仍保留在本机任务目录，不以历史报告代替本轮结果。

## 边界

未追加真实DeepSeek对照、生产支付联调、浏览器视觉验收、真实GPU硬挂死注入或业务身份PDF发布验收。常驻Worker未自动切换OCR后端，旧运行说明中的这些边界保持。通过本地验证不等于已部署、合入或生产验收。

本记录不自称远端强制保护生效。最终源SHA、远端推送及MR链接由本次PR正文记录；当前证据提交只增加文档与测试记录，不改变上述被测源码。
