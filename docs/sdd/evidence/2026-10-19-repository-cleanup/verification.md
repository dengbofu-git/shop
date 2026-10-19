# 2026-10-19 仓库资源清理与历史归档

范围：用户授权的“重复图片 → 无引用旧组件 → jQuery 重复加载 → 历史资料归档 → Worktree 收尾”。仅修改本地工作区，不提交、推送、合入或部署。开始时主工作区已有其他未提交和未跟踪内容，保持其在途状态。

## 实施结果

- 静态目录内 38 组重复图合并为单份，移除 39 份副本，减少 7,443,828 字节；保留的文件 SHA256 与原副本一致，映射见 [static-assets.json](static-assets.json)。数据库媒体 `media/` 不变。
- 移除无页面或应用引用的旧裁剪、截图、Bootstrap 和字体资源共 16 个文件；删除列表见同一清单。
- 两份支付模板仅保留原有 jQuery 3.1.1，一次加载；Cookie 插件顺序保留，移除重复的 3.3.1 文件，订单和支付请求逻辑不改写。
- ECharts 下载维护命令移至 `tools/fetch-echarts.ps1`，输出仍为 `client/static/js/echarts.min.js`。
- 2026-10-16 六批 Agent 评测和当天终端资料共 205 个文件移至 [历史归档](../../../../reports/archive/2026-10-16/README.md)，Git 对象与归档前逐项相同。[归档清单](../../../../reports/archive/2026-10-16/manifest.json)保留原路径、工作副本与 Git 内容 SHA256；两份可再生 Python 缓存不纳入正式归档。历史指标、失败、源码快照和嵌入的旧运行路径保持原样。
- 更新当前文档链接与评测工具默认入口；不移动 `docs/agent测试文本/`、`docs/sdd/evidence/2026-10-19-agent-100/` 的在途材料，不清除原始日志备份。
- core 升为 0.4.3，support_ai 升为 0.12.4，web 在已有 0.20.1 上增至 0.20.2，保留已有 changelog。

## Worktree 收尾

已重新获取 `origin/main`：`6ede7eaad5cce41752ca707db3726dfeacc6d821`。确认临时分支 `codex/web-merchant-dashboard-delivery` 的 tip `a683626d9d00019966b2cf8c5274b400531cb75d` 为 main 祖先，工作区干净且没有进程以该 Worktree 为工作目录。

归属元数据已本地备份后，用正常 `git worktree remove` 和 `git branch -d` 移除该 Worktree 与本地临时分支；没有使用 force。135 个再生缓存随工作区移除。远端分支和 PR 不操作，当前主工作区仍在 `codex/goods-sales-recommendations`。同时将规范中的无效下划线变量名改为 `teaSaasOwnerBranch`，已用 Git 配置解析验证。

## 实际验证

- `python client/tests/repository-cleanup-contract.py -v`：5 项通过，覆盖保留图片哈希、无旧资源引用、支付页库顺序、205 份归档完整性与当前对照工具输入。
- 项目 Python 3.9 环境：`manage.py check --settings=support_ai.test_settings`，0 个问题；两份支付 Django 模板编译、内联 JavaScript 语法及修改的 Python 文件解析通过。
- Node：现有 jQuery 3.1.1 与 Cookie 插件 `--check` 通过。
- `python tools/module_versions.py check`：15 模块，工作区文件均有归属。
- 起始快照比对：授权清理范围外的已有文件及在途资料未变化，真实 Git 暂存区未变化。

## 已有检查问题与边界

额外运行项目命名检查，4 项中 3 项通过；全仓名称检查在以下三份原已存在的在途文件报告旧命名，本次未修改它们：

- `docs/agent测试文本/2026-10-19-run-01/测试报告.md`
- `docs/sdd/evidence/2026-10-19-agent-100/verification.md`
- `docs/sdd/modules/merchant-operations/order-status-filters.md`

在独立临时索引中运行完整快照门禁，静态处理后被已有在途文档的行尾空白拦截；另发现 README 已有文件末尾空行并随本次索引链接整理。其余问题位于 `docs/agent测试文本/` 的两份新文档，继续保留原件，没有调整门禁或跳过检查。临时索引未替换真实暂存区，因此不能报告整仓交付门禁已通过。

未执行真实支付、订单写入、真实模型重放或业务数据库迁移；无 Migration 变化。本轮没有浏览器端到端验收，不把静态与模板检查记作支付业务验收。

## 后续授权的交付修正

用户随后明确要求先修复问题再提交。已按五份文档的最小预览清理四处行尾空白，并将三处命令中的本机解释器绝对路径显示为 `python`，说明其代表本轮项目 Conda 解释器。原始完整文档保存在本机 `.scratch/delivery-all-20261019/before/`。

四处空白属于超长／纯空白测试的可读 Markdown 展示，已在文档注明规范化；冻结 JSON 数据集、`results.jsonl`、实际输出、历史指标及失败判定没有改写。上文的失败记录保留其发生阶段，交付检查按最终提交另行确认。

同步最新主干时发现 core 0.4.3 已由主干使用，保留其原有 SDD 交付记录，本次清理顺延为 core 0.4.4；web 0.20.2 与 support_ai 0.12.4 保持不变。冲突仅涉及说明和版本元数据，双方历史均已保留。

最终 Git 对象审计发现，146 份归档文件存在 Windows 工作副本 CRLF 与 Git 内容 LF 的哈希差异；此前仅验证工作副本不足以证明跨平台可复核。已保留全部原始 `sha256`，补充 `git_sha256`、原 `git_blob` 和归档前源提交；205 份归档的 Git blob 与源提交 `09516bd6740db34a7f89e6c9e5b4ceb8abb83a95` 原路径逐字节相同。离线契约只允许换行转换，仍校验内容 SHA256 和原 Git 对象 ID，不修改归档载荷或放宽其他空白要求。

归档校验修复单独提交；按客户端测试归属将 web 顺延为 0.20.3，并保留 0.20.2 的静态资源清理记录。
