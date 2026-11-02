# MR交付后继续处理R08

日期2026-11-02（Asia/Shanghai）。基线`591a0ea721414ff33c0c4376282006543b213906`，分支`codex/core-sdd-remediation`。

## 已交付事实

用户授权“推送MR后继续处理”。此前99文件已精确提交为`d34c2e82f02cbedd762e33bfe3e30fd4feb3cea3`，正常merge最新main后源SHA为上方基线；main SHA为`b4df88540f1d42bb2adbb8aac6490ea337811715`。合并前后源码树相同，无冲突，未覆盖主干业务。

已推送并创建[MR31](https://github.com/dengbofu-git/shop/pull/31)，目标main，尚未合入。`python tools/git_policy.py verify --base origin/main`及真实pre-push通过：99文件、15模块、48项Python/JS语法。Django隔离系统检查无问题，模块归属及diff检查通过；业务证据按此前两个日期原记录阅读。

GitHub实际检查：Git policy与Django runtime均completed/success（[工作流](https://github.com/dengbofu-git/shop/actions/runs/41377165890)）。连接器创建PR因权限403失败，后改用仓库既有交付脚本及Git Credential Manager现有登录成功创建；凭据仅在内存中使用，未输出/落盘。

直接在原现场精确提交，推送前工作区干净，已交付增量不再留作dirty副本。无本轮新建临时Worktree/分支需回收；另一原有Worktree不属本轮，不动。收尾waiting-merge，不等待或自动合入；业务库、服务及部署未改变。

## 新增本地增量：可见咨询菜单

R08规格要求移动端可见菜单入口，基线历史条目只有续聊按钮、右键及Shift+F10。已为普通列表条目增加并列的44px菜单按钮，与聊天按钮不嵌套；点击菜单复用现有浮层，聚焦“移出列表”，关闭后归还触发按钮。列表根行保存会话标识，使去重、移出整行、分页和当前项样式保持。已移出列表不展示移出菜单，只允许恢复。

执行真实`loadHistory`和菜单函数的DOM回归先红后绿：修复前2项中1失败（没有第二个按钮）；修复后菜单2项+恢复7项共9项通过。覆盖菜单点击不续聊、焦点归还、独立原生按钮、恢复列表不出现移出菜单；测试未替代真实手机/键盘实机验收。证据日志位于本机`.scratch/rules-followup/mobile-menu-red.log`及`mobile-menu-green.log`。

`node --test <client/tests/*.test.js逐文件参数>`：109项全部通过，无跳过，日志`.scratch/rules-followup/post-pr-frontend.log`。模块归属检查15模块通过，`git diff --check`通过。JS语法与模板编译按本轮静态检查记录在source-snapshot.json。

web版本本地更新为0.36.2；MR31仍为0.36.1。本节新增源码/文档尚未提交或推送到MR31，也未重启启用。数据库迁移和真实模型/支付不在本次后续工作内；后续仍需手机及键盘实机验收、完整AC与单独授权运行启用。
