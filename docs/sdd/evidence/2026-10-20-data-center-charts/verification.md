# 数据中心图表库加载修复验证

日期：2026-10-20。分支：`codex/supplier-store-pages`；版本：web 0.23.2。本报告对应未提交工作区中的本轮增量，源文件 SHA256 见 `manifest.json`。保留此前店铺页面及其他任务的未提交工作。

## 问题与实现

用户截图显示五张图表统一报“图表库加载失败”，指标卡可用。原加载器只有 bootcdn 与 jsdelivr 两个外部来源，全部失败后无法绘制。现在先请求同源 `/static/vendor/echarts/5.4.3/echarts.min.js`，失败后沿用两个 CDN 及逐来源 5 秒超时、缓存统计重试与取消保护。模板更新脚本缓存参数，去除 CDN 预连接。统计 API、数据库和指标规则未改动。

ECharts 沿用原固定版本 5.4.3，从官方 npm registry 下载，完整 tarball 的 SHA512 与 `dist.integrity` 一致。原始 LICENSE、NOTICE、`licenses/LICENSE-d3` 与来源校验记录一并保存于静态资源目录。

## 本轮结果

- `node client/tests/operations-dashboard.test.js`：通过。覆盖本地来源优先、本地成功无 CDN 请求、本地超时／报错后回退、三源总失败与仅重试图表、接口并行、指标先显示、五张空闲绘制、周期切换、过期响应与空闲任务、取消释放、往返缓存恢复。
- `node --check client/static/js/operations-dashboard.js`：通过。
- `python tools/module_versions.py check`：通过，15 个模块，工作区文件均有归属。
- `git diff --check`：通过，仅有已有文件的 Git 换行转换提示。
- 隔离浏览器验收：8766 预览服务，独立 SQLite 与合成商家账号 `previewshop`，从工作台侧栏进入数据中心；状态显示“统计数据与图表已更新”。五个图表各有一个非零尺寸 canvas，`aria-busy=false`。年度切换月度后再次完成五图绘制；直接访问同一数据中心内嵌 URL 也成功，浏览器 error 日志为空。合成账号无订单，截图中的销售额为零，截图不代表真实经营数据。
- 本机 8000 只读 HTTP 验证：内嵌模板、初始化脚本、本地 ECharts 均返回 200；模板包含新缓存标记，脚本包含本地优先来源；HTTP 下载 bundle 的 SHA256 与仓库记录一致：`1156429a16a38cb8604dcc6518c19406d4226142d908f8edd2e3531443c54d19`。

浏览器截图：[charts-restored.png](charts-restored.png)。

## 验证边界

故障／超时回退使用确定性的加载器测试验证；真实浏览器验证成功加载本地库，未人为修改网络设置或阻断 CDN。未在真实商家登录会话中验收经营数据，也未执行全量后端测试、业务库写入、迁移、服务重启、Git 提交／推送、PR 或远端部署。
