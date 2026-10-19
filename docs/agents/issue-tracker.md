# 本地 Markdown 任务记录

适用于 tea_saas 的开发任务与问题拆解。借鉴 Store 的本地文件方式，采用本仓库现有 Git、模块版本和 SDD 规则；不引入外部任务平台或新的阶段门禁。

## 存放与权威

- 本机过程记录放在 `.scratch/<任务短名>/`，默认由 Git 忽略，不随仓库共享，也不提供跨机器备份。
- `spec.md` 只写本次目标、范围、约束、已有规格链接和验收方式；正式业务规则继续维护在 `docs/sdd/`，不复制出第二套有效规格。
- 每张任务单独放在 `issues/01-<短名>.md`、`issues/02-<短名>.md`，编号在同一任务目录内唯一；不要把多个任务合成一个文件。
- 需要交付或供他人复核的结论，写回对应 SDD、ADR 或 `docs/sdd/evidence/<run-id>/`；不能仅链接被忽略的本机文件。记录命令、结果和限制，避免写入凭据或真实客户数据。

## 状态和依赖

`Status` 是[分诊标签](triage-labels.md)，`Progress` 是执行进度，两者分开维护。进度取 `todo`、`in-progress`、`blocked`、`done`；`done` 必须附实际结果和证据。完成开发不等于已经提交、推送、验收或发布。

`Blocked by` 使用同目录任务编号，例如 `01, 02`，无依赖填 `none`。只有前置任务均完成才解除依赖；编号不存在或形成循环时先修正拆解。开始前检查是否已有执行者，再填写 `Assignee` 和 `Progress: in-progress`；文件记录不能作为跨进程原子锁，也不自动授权并行 Agent、Git 操作或部署。

分诊为 `ready-for-agent` 只表示需求足够明确，仍按用户实际授权执行。业务规则未定时使用 `needs-info`，并链接 CAP 开放问题；未达到当前 SDD 约定不能靠任务状态提升准入。

## 可复制模板

`spec.md`：

```markdown
# 本次任务名称

目标：
范围／不在范围：
依据：相关 CAP、规则、现有文档或用户要求
验收：可观察结果与定向验证方式
任务：issues/01-任务短名.md
待确认：无则填 none
```

`issues/01-任务短名.md`：

```markdown
# 01 任务名称

Status: needs-triage
Progress: todo
Assignee: unassigned
Blocked by: none
References: CAP 或规格路径；无则说明不适用

## 目标与范围

说明预期结果和允许修改的范围。

## 验收

- 可观察的完成条件及验证方式。

## 结果与证据

未执行。完成时记录实际命令、结果、限制，以及已回写的共享文档路径。

## Comments

按日期追加讨论、阻塞和决定；不覆盖已有记录。
```
