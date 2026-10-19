# tea_saas 协作与 Git 交付规则

适用仓库：`https://github.com/dengbofu-git/shop`。详细流程见 [Git 协作规范](docs/Git协作规范.md)，版本事实源为 `versions/modules.json`。

- 写入前检查当前分支、`git status --short`、`git worktree list --porcelain` 和实际 Diff。主干为 `main`，日常开发使用 `codex/<模块>-<任务>`；已登记个人分支为 `owner/dengbofu`。不得直接在 `main/master/dev` 开发。新任务不必新建分支；同一目标连续开发复用当前开发分支。
- 用户要求实现功能或配置时，可创建符合命名的本地开发分支；带着已有改动创建分支前须确认不会覆盖文件。跨已有分支切换、提交、推送、创建／合入 PR、部署分别按用户授权执行，不能从开发授权推导发布授权。
- 保留已有工作与他人代码；精确暂存本次授权文件，禁止顺手 `git add .`、自动 stash、reset、强推或重写共享历史。
- 仅提交／推送已有改动时进入 `DELIVERY_ONLY`：不扩展实现，不自动修复业务缺陷；允许在授权范围内正常同步主干并处理含义明确的冲突。历史迁移、业务选择不明或超范围冲突须停止说明。
- 普通提交只检查分支、授权范围、实际 Diff、误纳入文件、冲突标记、`git diff --check`、模块归属和版本；不隐式追加全量测试。提交信息采用 `<type>(<可选scope>): <中文主题>`。
- 实现变化须与对应模块版本和 changelog 一起提交；前后端分别评估，文档修订不单独强制升版。新增根文件或工具目录须登记模块归属。
- 推送前必须盘点全部 Worktree、确认当前分支工作区干净、获取最新 `origin/main` 并正常 merge 到源分支。检查完整待交付 Diff，运行 `python tools/git_policy.py verify --base origin/main`，按真实影响补充 Django、模板、静态资源及业务验证。Python/JS 语法通过不能当作完整构建或业务验收。
- 启用 `.githooks` 后，pre-push 会刷新 main，绑定当前完整 SHA，检查分支、干净现场、最新主干祖先关系、Python/JS 语法、模块版本和 Migration。失败不得用 `--no-verify` 或改配置绕过。未覆盖的业务验证须如实说明。
- 所有 PR 目标为 `main`，使用 `.github/pull_request_template.md`。标题用中文主题，正文保留“概要、改动、验证”，记录源 SHA、main SHA、实际命令与结果；未执行、失败、不适用分别写明。只授权推送时不代建或合入 PR，但提供可复制标题与描述。
- Worktree 仅用于真实并发或保护现场，创建时记录 `branch.<分支>.tea_saasOwnerBranch` 回收目标。交付前盘点全部产出，未归属改动不得混入；合入后确认干净、无人占用、提交已进入主干，再安全移除本次临时 Worktree 和分支，禁止强删。已有独有改动与其他任务产出继续保留；清理阻塞须明确报告，不能把远端合入等同本地完成。
- Django Migration 随所属 App 交付；历史脚本不得修改、删除或重命名，同 App 不得重复编号。新增迁移按实际数据库后端在隔离测试库验证，禁止连接业务库试跑或自动回退数据库。
- 版本标签为 `<模块>/v<版本>`，使用注释标签且指向已合入 `main` 的提交，发布标签不可覆盖。部署、发布、数据库迁移与验证分别报告。
- 全量验证用于用户明确要求、阶段集成或上线收口。需要修改业务语义时遵循当前 `docs/sdd/`；Store 来源规范仅供借鉴，不导入其 GitLab、Owner Registry、Flyway 或 SDD 阶段制度。
- 本地 Hook 可被跳过，Actions 需推送后才生效。只有 GitHub 实际启用保护规则并将 `Git policy` 设为必需检查后，才能声称远端强制合入门禁已生效。

## 任务记录与领域上下文

- 需要拆解任务或保留本机过程记录时，使用 [Markdown 任务约定](docs/agents/issue-tracker.md)和[分诊标签](docs/agents/triage-labels.md)；`.scratch/` 默认不入库。共享结论须回写 SDD、ADR 或正式证据，任务标签不扩大执行或 Git 授权。
- 涉及业务命名或架构取舍时，先读 [领域术语入口](CONTEXT.md)及[领域约定](docs/agents/domain.md)，按影响查阅 [ADR](docs/adr/README.md)。业务规则与阶段仍以本项目当前 SDD 为准。
- 查找 SDD ID 引用可运行 `python tools/sdd_refs.py CAP-AI-003`，说明见[引用检索](docs/agents/sdd-refs.md)。该命令只检索文本，不是 SDD 阶段检查器；历史证据默认排除，需要时显式加入。
