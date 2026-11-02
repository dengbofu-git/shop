# PII交付及后续方案引用修复

日期2026-11-02（Asia/Shanghai）。用户要求“创建MR，并继续处理”。本轮先冻结交付内容，再处理独立后续增量。

## 已交付

MR31已由GitHub核实合入main。本轮39文件增量精确提交，包含LangChain升级、PII策略/遗漏路径及可见咨询菜单，正常merge最新main后源SHA `c058524749e1c33843ec889f7071ef91d4c70a34`；main为`441e15deb68f89a99bb9e037b04d9d92dfaa3bca`。合并前后树相同，无冲突。

已推送并创建[MR32](https://github.com/dengbofu-git/shop/pull/32)，目标main，尚未合入。Git policy本地verify及真实pre-push通过：39文件、15模块、13份Python/JS语法检查；Django系统及模块归属检查通过。复用未被合并修改的原测试证据：Agent351项（343通过/8跳过）、原生MCP19项、前端109项；不是本次新跑同一套测试。GitHub CI实际状态以远端为准，本机记录不代替运行结果。

使用现有Git登录的仓库交付脚本创建PR（此前连接器已核实无写权限），未输出或保存凭据。直接提交原现场，推送前干净；无新Worktree需回收，另一原有Worktree不属本轮，不删。收尾waiting-merge。前序LangChain单独授权的真实合成试验按原证据阅读，不继承为本轮模型外发授权。

本MR模块为core0.14.0/support_ai0.32.1/web0.36.2，未新增或改写迁移，未统一重启、部署、合入或改变业务库。

## 创建MR后的新增本地修复

反例：公开方案身份`bundle-12345678abcd`符合现有生成格式（12位小写十六进制哈希），但通用8位长数字规则将其修改，造成正文/JSON模型提示/历史投影方案身份不一致，可能使方案切换或追问失效。

新增support_ai/test_pii_bundle_reference.py，3项先跑2失败。最小修复只在未知长数字回退检测中保留独立且格式严格有效的bundle引用；手机号、官方信用卡、邮箱等检测仍先执行，不能通过bundle前缀放行真实PII。错误长度/非十六进制不获豁免，服务端原有买家/会话/已保存方案检查不变，格式不是授权。

`manage.py test support_ai.test_pii_bundle_reference support_ai.test_pii_surfaces support_ai.test_pii_policy support_ai.test_bundle_optimizer support_ai.test_task_tools --settings=support_ai.test_settings --noinput`：44项全部通过。日志`.scratch/pii-bundle-green.log`，修复前日志`.scratch/pii-bundle-red.log`。同次后续完整Agent回归和静态源码/日志哈希见source-snapshot.json，使用合成SQLite及本机HTTP/SSE，无真实模型/业务数据调用。

后续本地support_ai0.32.2，未再次提交/推送，不包含于MR32当前源SHA。当前运行启用未验收；中文NER/URL内容/真实浏览器等既有限制保持，不由本次格式修复外推完成。

最终复核：MR32的Git policy与Django runtime均completed/success，尚未合入（[工作流](https://github.com/dengbofu-git/shop/actions/runs/41388248010)）。后续`manage.py test support_ai --settings=support_ai.test_settings --noinput`共354项，346通过/8跳过，无失败，16.270秒，日志`.scratch/pii-bundle-full.log`；2份Python AST、模块15归属及diff检查通过，源码/日志哈希见同目录source-snapshot.json。没有新增迁移、暂存或额外Worktree。
