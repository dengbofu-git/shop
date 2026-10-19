# 收藏与足迹定向验证

日期：2026-10-16，Asia/Shanghai。能力 CAP-CAT-004，规格 0.1.0；本切片引入版本 goods 0.3.0、web 0.5.0、core 0.1.4；最终定向回归使用的共享工作区联合版本见 manifest.json（包含其他并行任务的后续版本）。用户本次请求为实施依据，人工评审人未指定，能力阶段保留 IMPLEMENTING。

机器证据：[manifest.json](manifest.json) 记录命令、退出码、日志、HEAD 和当前工作区输入哈希。工作区原有大量修改，本次只扩展收藏／足迹相关代码和文档；HEAD 本身不代表被测实现。

| 验证 | 结果 | 证据与范围 |
| --- | --- | --- |
| SQLite 定向回归 | 10通过、2跳过 | [sqlite.log](sqlite.log)；跳过真实行锁并发测试 |
| MySQL 定向回归 | 12通过、0失败、0跳过 | [mysql.log](mysql.log)；独立唯一测试库，结束后已删除 |
| MySQL 并发 | 2项通过 | 同一SKU并发收藏只有一条；99条历史并发新增2件最终100条、两件新商品均保留 |
| 模型／迁移一致性 | 通过 | [migration-drift.log](migration-drift.log)，无缺失迁移 |
| JavaScript 语法 | 通过 | [js-syntax.log](js-syntax.log)，node --check退出0 |
| 模块版本清单 | 通过 | [versions.log](versions.log)，当前模块路径归属检查 |
| 本次相关文件diff空白检查 | 通过 | git diff --check按相关文件定向运行；全仓另有原有无关空白问题，未修改 |
| 本地业务库迁移 | 已应用goods 0009 | 命令manage.py migrate goods 0009 --database default --noinput；输出Applying goods.0009_browsinghistory_favorite... OK |

自动场景包括：缺失／无效 Token、停用买家、商家拒绝，JWT归属隔离及伪造owner字段，收藏幂等与数据库唯一约束，足迹重访置顶与100件裁剪，单条删除及清空不影响收藏，分页及非法参数，当前价格、下架商品、SKU删除级联、错误方法405以及页面模板路由。

## 浏览器验证

使用临时 SQLite、合成买家与14件商品，独立端口8001，验证脚本 [preview.py](preview.py)。没有向业务库创建测试用户或商品。

| 检查ID | 可见结果 | AC |
| --- | --- | --- |
| browser-navigation-pagination | 收藏首页14件、12卡片；下一页2件、2/2、下一页禁用；顶部入口正确跳转 | 01、07 |
| browser-detail-favorite | 从收藏进入详情显示已收藏；取消后按钮变收藏商品，再收藏后回列表持久保存 | 02 |
| browser-detail-recent | 成功详情访问后足迹出现1件，并显示已收藏；列表与详情状态一致 | 03 |
| browser-clear-empty | 清空后显示0件、暂无浏览足迹与去逛逛入口；返回收藏仍有14件 | 04 |
| browser-language-rtl | 中／英／阿内容切换，阿语RTL；金额保留人民币 | 08 |
| browser-mobile-layout | 手机宽度下单列，DOM实测clientWidth=scrollWidth=375，无横向溢出；结束恢复默认视口 | 01 |

截图：[收藏页](favorites.png)、[足迹页](recent.png)，均为合成验证数据。

## 限制

- AC-08的网络失败／401／403前端状态未逐一注入浏览器验证；相关接口身份拒绝均由两种数据库上的测试验证。
- 本次验证覆盖本切片及直接页面／路由／数据库依赖；没有运行全站AI、支付、短信、物流或生产发布验收。
- MySQL真实测试库验证唯一键与行锁行为，不代表所有部署环境版本、负载和故障场景均已验证。

复现命令（项目根目录）：`E:\miniconda\envs\tea_saas\python.exe docs/sdd/evidence/2026-10-16-buyer-activity/verify.py`。MySQL测试需要当前连接账号可创建／删除测试库，测试库名随机生成，不复用业务库。
