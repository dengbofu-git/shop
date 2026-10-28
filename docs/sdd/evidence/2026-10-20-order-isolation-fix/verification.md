# 五项多商家订单问题修复验证

日期：2026-10-20（Asia/Shanghai）。规则见[按商家独立下单与订单操作保护](../../modules/trade/merchant-order-isolation.md)。本轮先完成已有更新的提交／PR，再实现独立本地业务修复。

## Git 与运行状态

- 已有更新提交为 `1c3ca01`，同步 main 后通过 `25a08ee` 推送并创建 [PR #8](https://github.com/dengbofu-git/shop/pull/8)。
- PR 的首次 CI 在 Python 环境初始化失败；独立修复提交 `8e7ad35` 固定 Ubuntu 22.04 并脱敏三份共享证据，保留全部检查。远端 [Git policy](https://github.com/dengbofu-git/shop/actions/runs/39396157475/job/118539296477) 成功。GitHub 随后显示 PR 已被合并，合并提交 `2d8ccf9fc936ca4efeb36cadb797342d0b16e461`；本轮没有调用合并接口。
- 业务修复分支为 `codex/orders-merchant-repair`，基线已正常快进到上述 main 合并提交。为保护原工作区同时发生的其他页面更新，复用独立临时 Worktree 保留本轮代码；回收目标已记录，不自动清理有未提交产出的目录或分支。
- 本轮业务修改**未提交、推送、创建新 PR、执行 Migration、替换运行服务或部署**。PR #8 已合并不代表下面的业务修复已发布；访问原8000服务不能冒充使用本修复代码验收。
- 模块：orders 0.2.0、supplier 0.3.1、web 0.24.0；版本、changelog、接手版本表及 SDD 已同步。源文件指纹与基线见 [manifest.json](manifest.json)。

## 五项结果

| 问题 | 当前行为 | 验证 |
| --- | --- | --- |
| 采购车不拆单 | 两家店生成两笔独立标准订单和各自支付链接；每笔只含一个商家，Decimal金额和明细一致；同店多SKU合并 | 隔离测试与实际MySQL回滚探针通过 |
| 混合单发货 | 历史混合单在改动前返回409，不推进共享状态、不扣任一商家库存 | 两家分别尝试均409，原状态与库存不变 |
| 混合单删除 | 历史混合单返回409，双方明细保留 | 删除探针中双方明细仍完整 |
| 试单发货 | TrialOrder状态2变3，基础status保持原值，重复请求不再扣库存 | 模拟试单返回200，重复请求400 |
| 全款预售发货 | 检查定金／尾款均已付且PreSaleOrder状态4，发货后变5 | 模拟预售返回200；部分付款拒绝；重复请求400 |

历史混合单的修复方式是禁止危险整单操作，并非自动迁移为多笔历史订单。没有平台拆分按钮或自动处理历史账务；[修复前报告](../2026-10-20-multi-merchant/verification.md)中的五项失败保留为当时事实。

## 自动化结果

实际命令由本机启动器加载当前项目私有配置作为启动环境、将源码路径切到本轮Worktree，再运行测试。SQLite模式明确覆盖数据库为内存库；MySQL模式为每次运行生成全新 `test_order_isolation_<随机值>`，测试结束后销毁，绝不迁移业务库。原始本机命令保留于私有过程记录，共享 [checks.json](checks.json) 使用解释器／启动器别名。

- 受影响模块 SQLite：`DiscoverRunner` 的 labels 为 `orders supplier goods users.tests admin_panel.test_overview`，等效 `python manage.py test <这些labels> --settings=support_ai.test_settings --noinput`。运行117项，114通过、3项真实MySQL专用用例跳过；见 [sqlite-final.log](sqlite-final.log)。
- 隔离 MySQL：`orders.test_checkout supplier.test_order_actions supplier.test_analytics admin_panel.test_overview`，50项全部通过；包含两个并发发货请求实际竞争同一订单行锁，结果为一次200、一次400，只出现一次库存扣减／出库日志；见 [mysql-final.log](mysql-final.log)。这不代表完整商品模块在MySQL已全部验证。
- `node client/tests/order-payment.test.js`：独立金额与付款选择、单订单兼容、安全文本／链接、创建鉴权、继续付款只读、不重复创建及失败状态通过。
- `node client/tests/merchant-orders.test.js`：既有分类及动作回归、新子类型权限标记、混合单禁用通过。
- `node client/tests/checkout.test.js`：金额、币种、地址和确认页契约通过。
- `client/tests/merchant-orders-contract.py`：隔离SQLite真实视图响应传入Node，发货／删除后重查及模板／静态资源通过；fixture改为活跃账号以符合真实写入边界。见 [contract-final.log](contract-final.log)。
- Django `check` 无问题，`makemigrations --check --dry-run` 为 No changes detected。8个变化Python文件AST、JavaScript语法、模块归属和Diff检查通过；没有将这些静态检查当作业务验收。

故障回滚测试故意让第二个支付链接构造失败，日志会出现预期的503／RuntimeError事件；断言整批订单不存在且采购车不变，该事件不代表测试失败。其他故障注入日志同理，以测试最终结果为准。

## 实际业务库回滚探针

使用前轮用户授权创建的“模拟1、模拟2”和专用模拟买家，加载修复Worktree的真实路由、视图及JWT认证。RequestFactory直接调用路由，所有变更放在业务MySQL事务内结束回滚；没有把未提交代码部署到8000服务，也没有真实HTTP支付。

采购车读取和付款链接生成用本机确定性替代对象，不修改真实Redis、不调用网关。历史混合单只在事务内临时创建。5项原缺陷探针均通过；前后比较用户、订单、明细、各类型子表、商品、库存、日志、店铺和结算共11张表的内容指纹，全部相同。详见 [live-probes.json](live-probes.json)。之前保留的26笔独立模拟订单和原有业务记录未因修复验证发生持久改变。

## 交付边界

未进行真实浏览器视觉验收、真实支付／退款、模型调用或全站全量测试。新页面通过模板渲染和Node行为契约验证；实际金额／状态在隔离数据库及回滚探针验证。未新增数据库幂等键、库存预留、可信支付回调、统一库存权威或子类型完整买家后续流程，不宣称已完成生产支付／履约闭环。

## 2026-10-23整合补记

以上为旧工作区原始历史结果，保留当时未交付状态、重复发货400和创建即支付链接等记录；本轮已采用主工作区预留／幂等下单／可信支付链路，旧可用隔离及子类型履约规则被吸收，重复发货现为幂等200。最终规则与验证见[整合证据](../2026-10-23-workspace-integration/verification.md)，不能将本页历史回滚探针视为本次业务库验证。
