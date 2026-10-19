# 废弃管线与冗余资源保守清理

日期：2026-10-19，Asia/Shanghai。用户要求检查项目废弃管线与冗余代码并精简，严格不得影响现有功能。

## 范围与判定

以本次开始时的实际工作区为基线，不以 Git HEAD 覆盖其他未提交工作。检查 326 个项目源文件，包含 173 个 Python 文件及前端模板、脚本、样式、部署和工具代码；排除虚拟环境、第三方安装目录、Migration、历史报告与历史证据。另用仓库引用搜索复核候选文件和导出名称。

删除条件：文件没有被当前模板、脚本、样式、Python、配置或测试引用，并已检查静态依赖、CSS import 及前端动态加载方式。没有按“文件名旧”“函数看似未用”或“重复样式”批量删除代码。

## 本次删除

共 19 个孤立静态资源、469,678 字节（约 458.7 KiB）。原文件路径、大小及 SHA-256 见 [清单](manifest.json)。

| 类别 | 删除文件（均位于 `client/static/`） | 依据 |
| --- | --- | --- |
| 旧页面样式 | `css/404.css`、`css/foodstore.css`、`css/itemCat.css`、`css/item_food.css`、`css/myCollect.css`、`css/myOrder.css`、`css/orderInfo.css`、`css/personage.css`、`css/search.css`、`css/slide.css` | 当前模板与样式没有加载引用；现行商品、订单、收藏页面使用各自的工作台资源 |
| 旧公共样式 | `css/footer.css`、`css/header.css`、`css/modal.css` | 无模板、CSS import 或脚本加载引用；保留当前公共主题及实际使用的头部样式 |
| 未接入脚本 | `js/collect.js`、`js/common.js`、`js/router.js` | 无加载引用；旧收藏 DOM 实现、ActiveX XHR 工厂、独立 SPA 路由封装没有当前调用者；现行收藏脚本及 Django 多页面路由保留 |
| 重复库 | `js/jquery-1.11.3.js`、`js/jquery.min.js`、`js/js.cookie-2.2.1.min.js` | 没有当前加载引用；其他实际使用的 jQuery 版本和 cookie 插件保留 |

原始字节副本另保存在本机被忽略的 `.scratch/retired-code-cleanup-20261019/removed-files/`，不作为跨机器恢复或交付依赖。

## 明确保留的候选

- Agent 的语义规划、有限任务模板、受控执行、查询改写、多查询融合、补检、重排、合规检查均仍在当前调用链上，保留实现及开关。
- `IntentScores`、`DialogueResolution` 虽有旧诊断用途，仍被当前回归／诊断代码导入，保留合同。
- `customer_required`、`search_knowledge_text` 暂未找到业务调用者，但属于公开辅助接口，未证明外部调用及动态使用边界，保留。
- `WeiboProfile`、旧偏好模型及偏好迁移命令涉及历史数据或迁移兼容，保留；历史 Migration 不变。
- 旧页面地址的重定向、`terminal_login.html` 兼容入口、普通注册页 `register_sms.html` 保留。
- `base.css`、`index.css` 等虽有重复规则，但仍被页面加载，不能在未核对层叠和布局前直接合并。
- 未使用导入仅列为候选，不据此更改模块导出或导入副作用；CI、诊断工具、评测脚本、历史报告均保留。

## 本次检查与结果

| 检查 | 实际结果 |
| --- | --- |
| 与任务开始时源文件快照对照 | 只有允许清单中的 19 个文件被删除；其余 307 个源文件内容一致，见 [保留文件摘要](preserved-sources.json) |
| Python AST 语法检查 | 173 个项目 Python 文件通过 |
| `python manage.py check` | `System check identified no issues (0 silenced)` |
| Django `get_template` 编译 | 38 个当前模板通过；未渲染业务页面或调用业务 API |
| `python tools/module_versions.py check` | 15 个模块归属检查通过 |
| 本次删除路径及版本文件的 `git diff --check` | 通过 |

web 版本从 0.17.0 更新为 0.17.1，追加 changelog，旧版本说明保留。本次没有修改后端代码、URL、现行模板或仍在加载的脚本／样式，也没有修改数据库或运行环境配置。

本次未新增或运行测试，未执行浏览器端到端验收、真实支付、模型调用或生产验证。以上证明本次源文件范围与静态依赖保持，不将其表述为全系统业务验收或绝对无缺陷保证。未提交、推送或部署。
