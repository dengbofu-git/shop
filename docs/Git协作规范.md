# tea_saas Git 协作规范

适用日期：2026-10-16。仓库为 `https://github.com/dengbofu-git/shop`。

本规范借鉴 Store 的现场保护、按影响验证、同步后绑定最终提交、PR 证据与 Worktree 收尾规则，适配本项目的 GitHub、Django 和模块独立版本。当前集成主干继续使用 `main`。

## 1. 分支和授权

- `main`：集成主干，通过 PR 合入，不直接开发或推送。
- `codex/<模块>-<任务>`：默认开发分支，例如 `codex/goods-stock-fix`；名称使用小写字母、数字和 `._/-`。
- `owner/dengbofu`：登记的长期个人开发分支。新增个人分支需同步调整本规范、AGENTS 和检查器。
- 同一目标连续开发复用分支，分支不随聊天创建。临时 Worktree 只用于并发或现场保护。
- 本地开发、提交、推送、创建 PR、合入 PR、标签发布和部署分别授权。实现任务不自动授权推送。

写入前运行 `git branch --show-current`、`git status --short`、`git worktree list --porcelain`。保留脏现场，精确暂存授权文件，不批量丢弃、stash 或清理。Worktree 建立时记录 `git config --local branch.<分支>.tea_saasOwnerBranch <回收分支>`；交付前核对其独有提交及未提交工作，收尾只安全清理已完整交付且无人使用的本次对象。

## 2. 提交信息和版本

格式：`<type>(<可选scope>): <中文主题>`，标题最长 100 字符。type 为 `feat/fix/docs/style/refactor/perf/test/build/ci/chore/revert`；scope 推荐使用 `versions/modules.json` 中的模块名。

```text
feat(goods): 增加茶类筛选
fix(support_ai): 修复会话指代读取
chore(core): 配置 Git 协作门禁
docs: 更新项目接手说明
```

正文默认中文，技术标识保留原样。Git 自动产生的 Merge 和 Revert 标题允许原格式，不追溯改写旧提交；PR 标题必须符合上述中文格式。

模块实现变化必须递增版本，并同时修改对应 changelog；前端与后端分别评估。门禁对 `.py/.js/.css/.html/.sh/.ps1/.yml/.yaml` 变更执行版本检查；其他运行配置和依赖变更仍须人工按影响评估。删除实现文件同样需要升版。纯文档不强制递增版本。

## 3. 本地配置与 Hook

```powershell
python tools/git_policy.py install
git config --local --get core.hooksPath
git config --local --get commit.template
```

安装仅修改当前克隆的 `core.hooksPath=.githooks` 和 `commit.template=.gitmessage`，遇到已有不同配置停止，不覆盖。新克隆和其他开发者需各自安装；Linux/macOS 安装时为 Hook 增加执行权限。

| 入口 | 实际检查 |
| --- | --- |
| pre-commit | 开发分支、精确暂存快照、Diff 空白、冲突标记、敏感路径、模块归属／版本、迁移不可变和编号 |
| commit-msg | type、可选 scope、中文主题和长度 |
| pre-push | origin 地址、当前分支最终 HEAD、干净工作区、刷新 main、主干祖先、完整待交付 Diff、上述检查和 Python/JS 语法；检查后再核对 main／HEAD／现场 |

提交检查读取暂存内容，交付检查读取提交对象，不用未暂存文件冒充交付内容。敏感检查只覆盖文件路径，不是完整凭据扫描；严禁在源码、文档、示例和日志中写入真实密码、Token、私钥。

手动检查：

```powershell
# 检查精确暂存内容；verify 额外检查 Python/JS 语法
python tools/git_policy.py check
python tools/git_policy.py verify
# 检查主干到当前提交的完整差异（先同步最新 main）
python tools/git_policy.py verify --base origin/main
python tools/module_versions.py check
```

`check` 不运行全量业务测试；`verify` 的 Python AST 和 Node `--check` 只是语法检查，不导入 Django、不渲染模板、不验证数据库或模型服务。HTML、CSS、Django 系统检查及业务验证按实际影响补充，在 PR 中写明结果或未执行原因。

## 4. 推送和 PR

先精确提交授权改动，工作区干净后再同步主干：

```powershell
git fetch --no-tags origin refs/heads/main:refs/remotes/origin/main
git merge --no-edit origin/main
# 有冲突时保留双方意图，完成正常 merge，再读取最终 SHA
git rev-parse HEAD
python tools/git_policy.py verify --base origin/main
# 按实际影响补充 Django、模板及业务验证
git push -u origin codex/core-example
```

Hook 内部还会刷新 main；main 前进时停止推送，重新同步再检查，不在检查后隐式 merge。只允许推送当前分支 HEAD，不允许直接推 main、推其他分支、批量镜像或在普通交付入口删除远端引用。禁止强推和 `--no-verify`；远端同名分支分歧用正常 merge 解决。

PR 目标必须是 `main`。使用 `.github/pull_request_template.md`，保留“概要、改动、验证”，说明功能影响、模块版本、源 SHA、main SHA、命令与实际结果。已有同源同目标开放 PR 时更新原记录；只授权推送时提供可复制 PR 文案，不代建或合入。

只交付已有改动时冻结实现（`DELIVERY_ONLY`），检查失败只报告阻塞，不擅自修复其他业务。普通提交不追加全量测试；推送前按受影响范围取得有效验证证据，源码、依赖、配置或合并结果变化则重验，覆盖内容未变时注明复用依据。

## 5. Django Migration 与发布

历史 Migration 不改写，修正使用新增迁移。同 App 的编号不得重复；检查读取完整迁移目录，即使本次不是数据库任务也会校验。Django 分支合并迁移或特殊历史修复先由维护者制定明确方案，不用改编号或跳过门禁处理。

新增迁移需在隔离测试库按真实数据库后端验证迁移计划与执行；MySQL 与 PostgreSQL 分别确认。静态检查不能证明迁移可执行。数据库上线和回退须单独授权、备份并制定方案，不自动对业务库执行操作。

模块标签使用 `<模块>/v<版本>` 的不可变注释标签，目标提交必须已进入 `origin/main`，标签中的版本与目标提交清单一致。按 [模块版本管理](模块版本管理.md) 创建标签；普通 Hook 仅允许发布当前清单中匹配且已经合入主干的版本。删除或特殊历史标签由维护者单独处理，不复用日常推送入口。

## 6. GitHub Actions 与远端保护

`.github/workflows/git-policy.yml` 在面向 main 的 PR（含标题编辑）和 main 推送时执行。PR 检查中文标题和源分支，按 merge-base 到源 SHA 检查交付内容；main 推送检查本次集成完整 Diff。治理回归测试独立运行，不连接业务数据库，不使用仓库 Secret。

Actions 上传后才会运行；本地 Hook 可以被跳过。维护者在 GitHub 的 Settings → Rules → Rulesets 为 `main` 启用：要求 PR、要求分支最新、将 `Git policy` 设为必需状态检查、禁止 force push／删除；Review 数量按实际团队设置。首次 Actions 运行后再选择对应检查名，避免配置不存在的检查。

工作流事件与分支过滤依据 [GitHub 官方文档](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow)。本仓库文件不能自动开启服务端保护；未通过 GitHub 权限实际配置并核实前，只能报告“本地配置／工作流已准备”，不能声称远端强制门禁已启用。
