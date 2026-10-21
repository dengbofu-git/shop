# 订单内评价后续交付验证 — 2026-10-21

PR10已于本日合入main，本次为后续修正的新PR，目标仍为main。现有独立交付worktree用于保护原工作区；其他工作区的采购、收藏、店铺和拆单／发货改动不在范围内。

- 被测实现提交：`96d034224d4e5e19e7f07dc72dad155a10d96963`；正常合并的main：`dc9665971c35a2750e1b37328e3697f0afc0e800`，合并无冲突。
- 最终源SHA见PR正文；本报告之后只提交文档及实施证据的命令路径规范化，9份相关实现文件的SHA256见[清单](order-review-delivery-manifest.json)。
- 模块版本：web 0.25.2、engagement 0.1.1，均有对应changelog。其余模块版本不变；相对main无新增Migration。

## 验证结果

命令中的python指项目Python3.9环境，node指当前配置的Node运行时，避免将本机绝对环境路径写入共享文档。

| 范围 | 实际命令与结果 |
| --- | --- |
| SQLite业务回归 | `python -X utf8 .scratch/engagement-publish-20261021/run_checks.py sqlite`：102项，97通过，5项既有后端限制跳过 |
| MySQL业务回归 | `python -X utf8 .scratch/engagement-publish-20261021/run_checks.py mysql`：随机隔离MySQL测试库37项全部通过；不连接业务库试跑 |
| 前端传输与文本渲染 | `node --test client/tests/engagement.test.js`：4项全部通过 |
| Django与模型 | `run_checks.py check`：check无问题、makemigrations --check --dry-run无漂移 |
| 模板 | 初始化上述测试设置后，get_template逐个渲染buyer_orders、buyer_reviews、buyer_messages、merchant_reviews、admin_reviews：5份通过，买家独立评价导航不存在 |
| 治理 | `python -m unittest tools.tests.test_git_policy tools.tests.test_project_identity tools.tests.test_module_versions -q`：Git治理23项及其余5项通过，1项命名失败；规范化2份新文档的本机环境路径后，单独重跑命名／模块归属6项全部通过，未改治理规则或跳过Hook |
| 提交对象检查 | `python tools/git_policy.py verify --base origin/main`：19变化文件、16模块、5份Python/JS语法通过；最终文档提交后再复查完整提交对象 |

首次静态门禁因系统临时目录访问受限而失败，改用本任务可写临时目录后通过；首次附加模板脚本因相对runpy路径导致临时目录位置错误，改用绝对脚本入口后重跑通过。两项均为验证环境修正，无业务代码修改。验证原始输出保留在本机忽略目录。

## 业务与本地启用证据

- [订单入口与隔离浏览器验证](order-entry-verification.md)：取消独立买家评价入口，仅显示本人订单商品评价；去掉无法关联本单商家时的总消息中心兜底。
- [本地迁移启用](local-activation.md)：经用户单独授权，备份、恢复验证、两份原有迁移和8000重启均已完成；25项只读HTTP检查通过。
- [历史归属核验](historical-review-activation.md)：经另一次单独授权，按连续完整MySQL行日志核验并补齐31笔已完成订单的35个商品项；29项买家API资格通过，6项非买家限制保留，1笔无商品明细订单未补造。
- 当前买家已完成订单页面已出现11个评价入口，可打开评分和评论表单。真实评价没有自动生成；业务库SQL、原始行日志、私密执行清单、真实订单截图均不交付。

历史报告中的“未提交／未迁移”描述保留为当时状态，本报告及后续PR记录为当前交付状态。当前授权仅推送、创建PR；不合入PR、打标签或远端部署。跨店拆单与发货修复不在本次范围，不追加全项目集成测试或真实支付测试。
