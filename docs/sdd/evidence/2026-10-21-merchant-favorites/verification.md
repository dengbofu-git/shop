# 商品与商家收藏分区

日期：2026-10-21。用户要求“我的收藏要区分收藏商家和商品”。实现版本 goods 0.6.0、web 0.26.0。

## 实现范围

- 收藏页提供商品／商家两类，分别分页、计数及移除；商家列表显示公开名称、Logo、简介与可访问状态，商品保持原详情和操作。
- 店铺页新增收藏商家／取消收藏，使用当前买家 JWT。商家收藏独立存表，不自动收藏其商品，不写商品浏览足迹或 AI 偏好。
- 新收藏仅接受有效、活跃且有已发布页面的商家；下线后仅保留收藏时的公开名称／Logo快照并支持取消，不读取草稿或账号资料。

## 已执行的检查

| 命令／检查 | 结果 |
| --- | --- |
| `python manage.py makemigrations goods --check --dry-run --settings=support_ai.test_settings` | No changes detected in app goods，模型与新增迁移一致 |
| `node --check client/static/js/buyer-activity.js` | 通过，仅语法检查 |
| `node --check client/static/js/store-page.js` | 通过，仅语法检查 |
| 本轮文件 `git diff --check` | 通过 |
| 新增迁移在随机名称的全新 MySQL 临时库执行 | 通过；创建 goods_merchant_favorite 表，核对 user_id／merchant_id 外键及组合唯一约束；临时库已删除 |
| 建表前业务库迁移计划只读核对 | 仅待执行 goods.0011_merchantfavorite；当时新表尚不存在 |

隔离迁移进程在 Django 初始化之前替换 default 数据库名；包括历史数据迁移在内的全部执行只针对新建临时库，未对业务库执行迁移或写入模拟数据。迁移结构检查不代表收藏业务回归通过。

结构化结果见 [隔离迁移摘要](migration-result.json)。

## 已授权的本地启用

用户随后明确答复“允许创建新表并启用预览”。范围检查脚本确认本地 default 连接为既有3306业务库、仅有 goods.0011 待执行后，调用 Django `migrate goods 0011_merchantfavorite --database default --noinput` 的等价管理命令；结果为 Applying goods.0011_merchantfavorite... OK。

实际仅新增 `goods_merchant_favorite` 表，组合唯一约束已核对，目标迁移已完成；没有执行其他模块迁移或回填现有商品收藏、订单。已重启本地预览后端。结构化结果见 [本地启用摘要](local-enable-result.json)，数据库名在公开记录中使用占位符。

## 尚未执行

未运行功能自动化测试或登录后的浏览器操作验收；HTTP页面可访问与未登录API返回401仅用于确认服务加载，不代表收藏业务验收。没有提交、推送、发布或生产部署，不自动逆迁移。
