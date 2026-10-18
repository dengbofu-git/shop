# 卡片交互验证

日期：2026-10-18；工作区 `codex/users-unified-login`，web0.8.0。规则见[卡片操作分层](../../modules/catalog-content/card-interactions.md)。未提交、推送、迁移或部署；其他任务的既有工作保留。

## 截图与观察

1. 原卡片：用户明确提供的[截图](user-before.png)显示深色悬浮层挡住采购按钮、收藏入口层级不清。原整卡触发采购和“溯源”误跳详情另由源码确认。
2. 桌面精选：页面12张卡片，悬浮说明层数量0；DOM矩形检查卡片内按钮及溯源入口两两交叠数0。实心采购、描边收藏与下方预览／溯源分别显示。效果见[桌面截图](desktop.png)。
3. 手机精选：浏览器视口设置390×844，滚动条扣除后内容宽375px；页面scrollWidth=clientWidth=375，无横向溢出。四个操作高度均44px，见[手机截图](mobile.png)。阿语RTL同宽度无横向溢出，主按钮高度44px。
4. 行为检查：点击商品说明，采购车计数仍为0、预览未打开；点击快速预览显示当前商品名称及完整规格。Esc关闭后，document.activeElement回到原预览按钮。采购列表12张卡片，每个主操作行含2个按钮，预览能打开；英文文案为Quick preview，溯源目标为trace.html?code=TR-64。检查后恢复中文及默认视口。

上述为当前本地8000服务的浏览器检查；没有为验证而提交真实采购、收藏或支付写请求，不能据此声称已通过真实买家采购／收藏持久化端到端验收。收藏API及权限沿用现有实现，原后端用例保持独立证据；本轮只修改卡片按钮挂载位置。

## 聚焦回归

- JavaScript语法检查覆盖buyer-workbench、buyer-products、buyer-favorites。
- `node client/tests/unified-login.test.js` 通过，保护同一工作区统一登录及平台入口守卫。
- `python manage.py test users.tests support_ai.test_telemetry --settings=support_ai.test_settings --noinput`：27项通过。隔离SQLite及合成数据，不连接业务库或外部模型。预期异常日志不影响最终OK。
- 模块归属、Diff空白、Django系统检查和文档链接完成后记录于同目录manifest。

边界：溯源仍为演示，现有跨页面价格／币种差异没有在本次调整；推荐小卡片、支付、真实模型、生产环境和全站对象权限不在本次验收范围。
