# 跨境茶叶 SaaS 平台调整验证

日期：2026-10-18。环境：Dadashop Python环境、Node；数据库验证只使用 `support_ai.test_settings` 的隔离SQLite内存库。

| 命令／检查 | 实际结果 |
| --- | --- |
| `python client/tests/tea-saas-contract.py` | 25个页面外壳通过名称和范围检查；受保护页面允许登录重定向后单独验证模板；原演示页普通／嵌入地址均404；专用资源与初始化命令不存在；SDD映射为8个域、24个能力、28项功能 |
| `node client/tests/tea-saas-brand.test.js` | 中英阿SaaS名称、销售趋势使用真实monthly.sales、履约状态使用订单数量、空数据不造示例值，均通过 |
| `python manage.py test supplier.test_analytics --settings=support_ai.test_settings --verbosity 1` | 8项通过，包含完成率、在途订单数及已付款统计原有回归 |
| `node client/tests/unified-login.test.js` | 登录分流与平台入口保护回归通过 |
| `node client/tests/buyer-products-pagination.test.js` | 全部／分类10件分页、SKU无遗漏及语言切换回归通过 |
| `python manage.py check --settings=support_ai.test_settings` | 无问题 |
| `python tools/module_versions.py check` | 15个模块，全部跟踪文件有归属 |
| 受影响Python AST、JavaScript `node --check`、`git diff --check` | 通过；不作为完整业务验收 |

本次没有新增Migration，历史迁移文件未改写；业务数据库、已有账号、商品和订单均未修改。历史证据和版本记录保留。未执行浏览器视觉验收、真实邮件发送、支付调用、生产部署、Git提交或推送。
