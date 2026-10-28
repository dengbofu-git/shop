# 商家首页待办与消息验证

日期：2026-10-22。实现规格：[待办与消息](../../modules/merchant-operations/workbench-tasks-messages.md)。验证当前本地增量，尚未绑定交付提交 SHA。

## 已执行

- `python manage.py test supplier.test_workbench supplier.test_analytics --settings=support_ai.test_settings --noinput` 对应的 DiscoverRunner：隔离内存 SQLite，18 项通过，其中新增待办／消息 10 项、原销售统计 8 项。
- 相同测试标签使用 `engagement.test_mysql_settings`：随机命名的独立 MySQL 测试库，18 项通过，框架创建与销毁该临时库，未在业务库试跑迁移。
- `node --test client/tests/merchant-workbench-feed.test.js`：6 项通过，覆盖真实零值、加载失败与重试、过期响应、账号切换、取消请求、无令牌、权限失败、正文安全渲染、入口白名单及三语状态。
- Django `check` 无问题；`makemigrations --check --dry-run` 无模型变化；`merchant_dashboard.html` 模板编译成功。
- 本地 HTTP 与业务库只读比对：6 个有商家入口的有效账号，分别检查全部待发货订单、待结算、未读会话、总数、占位 null 与订单归属；全部一致。未生成测试订单、咨询或运单，未修改业务记录。空店铺返回 0 与空列表。
- 本地浏览器使用已有模拟商家登录：显示数据库中的 4 笔待发货、1 笔待结算、0 个未读咨询，总数为 5；待发货入口在商家 iframe 内选中待发货分类，显示 4 笔；结算入口展示真实记录，返回首页重新刷新，登录身份保持一致。中文／英文／阿拉伯文切换正常，窄屏卡片可读；未接入项目只保留模板注释。
- `python tools/module_versions.py check` 通过；本轮相关文件 `git diff --check` 通过。保留工作区其他同期改动，未暂存任何文件。

## 环境与范围

使用项目既有 Django 3.2.12／Python 3.9 环境、现有 Node 运行时、现有 MySQL 服务。运行过程日志及业务数据只读核对原始结果保存在本机忽略目录，不作为共享资料发布。

本轮未执行全量应用回归、生产部署、Git 提交、推送或 PR。未新增数据库迁移；本地启动提示的 ai_storage 既有待迁移项未执行，与本接口无模型依赖。商品审核、独立售后和通知事件流仍未实现，缺失流程保留代码注释占位。
