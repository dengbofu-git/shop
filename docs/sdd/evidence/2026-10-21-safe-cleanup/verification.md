# 2026-10-21 不改变当前功能的仓库清理

## 范围与保留

用户授权在不影响功能的前提下清理。起始提交为 `25a08ee29e23ce1bd479951e5860b44c9dfb2a89`，当前分支 `codex/orders-merchant-isolation` 已有商品页及其他在途改动；本次不提交、推送、切换分支、清理Worktree或修改暂存区。

- 删除177张旧静态图片，共29,374,136字节。路径、SHA256及保留理由见 [manifest.json](manifest.json)。先做源码／模板／样式／工具引用筛查，再解码URL检查含空格支付图片，并保留测试与历史证据引用、此前图片去重的保留件。未修改任何当前页面、JavaScript或CSS。
- 对当前配置的MySQL使用只读事务，扫描商品、资讯及店铺15张表的文本／JSON字段，共4,179行；未发现入选图片引用。仅保存匹配结论，不输出业务内容；事务最终rollback，没有业务数据写入。首次沙箱连接不可用，在获准执行的同一只读连接中完成检查。
- 保留 `client/static/images/myOrder/timg .jpg`，支付页通过 `timg%20.jpg` 引用。保留4份现有首页CSS背景、商品占位图、当前Logo、全部 `media/` 文件以及42份有测试／历史引用或历史保留约束的候选图片。异常编码文件继续保留。
- 将旧 `goods_data.json` 原字节移至 `reports/archive/legacy-catalog/` 并登记商品模块归属；不重跑造数、不连接数据库导入。
- 删除仅含导入和已注释后台注册的 `news/admin.py`；从库存及物流视图分别移除一个未使用服务类导入。查询处理、权限装饰器、路由、模型与服务方法没有改写。
- 保留商家AI初始化入口、历史微博模型、StandardOrder模型，以及未接线库存／物流服务；不改变数据库结构，不修改任何Migration。

所有删除及修改原件已备份到本机忽略目录 `.scratch/safe-cleanup-20261021/original-files.zip`，并逐项核对备份SHA256。该备份不是跨机器共享资产；原图片仍可从起始Git提交恢复，清单记录了所有路径。

## 版本

基于工作区现有版本递增，保留在途changelog：web `0.24.1 → 0.24.2`、goods `0.5.1 → 0.5.2`、inventory `0.1.0 → 0.1.1`、logistics `0.1.0 → 0.1.1`、news `0.1.1 → 0.1.2`。

## 验证

- `python client/tests/repository-cleanup-contract.py -v`：5项通过；历史归档内容、原图片去重保留件、支付jQuery顺序和当前评测资料入口均保留。
- 项目Python 3.9运行 `python manage.py check --settings=support_ai.test_settings`：0问题。
- `python manage.py test goods.test_images merchant_ai.tests --settings=support_ai.test_settings --noinput`：18项通过，使用隔离SQLite，覆盖图片优先级、上传、占位／虚拟图、商品／购物车／订单投影及商家助手入口。首次运行被沙箱系统临时目录的WinError 5拦截；重跑通过同一Django管理入口，将 `tempfile.tempdir` 指向 `.scratch/safe-cleanup-20261021/test-temp`，未调整测试断言。
- 一次性完整性检查：全部入选图片名称在URL解码后的当前源码中无引用；每份保留静态／媒体文件的SHA256与清理前一致；旧样例工作副本与备份字节相同，规范化换行后与原Git blob相同。两份视图AST除删除的导入外完全一致。
- 原工作区逐文件SHA256对账：本次精确范围之外的已有文件／在途改动未变化，所有Migration和媒体字节未变化；真实暂存区与开始时的空暂存区一致。
- `git diff --check`：通过。`python tools/module_versions.py check`：15模块，工作区文件均有归属。
- 项目命名与模块归属共6项回归：5项通过，1项命名扫描失败。失败定位到原已存在且本次SHA256未变化的 `docs/sdd/evidence/2026-10-20-store-pages/activation-summary.json`、`local-activation.md`、`mysql-expanded.log`；不修改原始证据，不将整仓命名检查记为通过。

尚不能由静态无引用结论推断真实支付、真实模型或其他部署环境已验收；本次不执行这些操作。数据库检查仅针对本机当前配置的商品／资讯／店铺数据快照，不代表其他部署或未来写入的路径。

## 后续授权的独立交付

用户随后要求推送并创建PR。主工作区的采购页等在途改动继续保留；复用本聊天已附加且干净的Worktree，从最新 `origin/main` 的 `2d8ccf9fc936ca4efeb36cadb797342d0b16e461` 创建 `codex/web-safe-cleanup`，仅迁入本轮清理。最新主干没有引用177张待删图片；所有图片在删除前均重核SHA256。

工作区中的0.24系列采购改版尚未纳入本PR，因此交付版本从实际主干递增：web `0.23.2 → 0.23.3`、goods `0.5.0 → 0.5.1`、inventory `0.1.0 → 0.1.1`、logistics `0.1.0 → 0.1.1`、news `0.1.1 → 0.1.2`。原阶段版本记录保留其工作区语境，不代表PR包含采购改版。最终主干已包含PR #8的证据脱敏修正，命名检查按此快照重跑。

独立交付快照实际验证：暂存范围严格为192个路径（含177张删除图片）；`python tools/git_policy.py verify` 通过，15模块、2项Python语法检查。命名及模块归属6项、清理契约5项、商品图片和商家助手18项均通过；Django系统检查0问题。Django通过项目Python 3.9、内存SQLite、工作区临时目录及测试专用占位环境变量执行，不复制业务凭据或调用真实服务。首次独立Worktree验证因缺少必填配置停止，补齐测试占位值后完成；未放宽任何断言。
