# 用户昵称定向验证

日期：2026-10-22。实现工作区分支 `codex/orders-merchant-isolation`；交付使用已有干净工作区 `codex/engagement-delivery`，隔离其他任务改动。模块增量为 core 0.6.2、users 0.4.0、engagement 0.1.3、web 0.28.0；实现工作区 web 后续并行布局修订已到0.28.1，保留其变更且不混入本轮交付。core在同步主干0.6.1后递增为0.6.2。本轮未进行生产部署。

## 已执行

使用项目既有 Python 环境及 Django 3.2.12。私有运行器在 `.scratch/user-nickname-20261022/run_checks.py`，无凭据写入本记录。

| 命令／范围 | 结果 |
| --- | --- |
| `python .scratch/user-nickname-20261022/run_checks.py sqlite` | 65项，64通过，1项仅MySQL事务测试跳过 |
| `python .scratch/user-nickname-20261022/run_checks.py mysql` | 65项全部通过；真实MySQL独立随机库，迁移执行后运行用例，结束销毁 |
| `node --test client/tests/profile-nickname.test.js client/tests/engagement-messages.test.js client/tests/engagement.test.js` | 26项通过，含昵称编辑及已有消息行为；不是全站构建 |
| `python .scratch/user-nickname-20261022/run_checks.py check` | Django系统检查通过，makemigrations检查无模型差异，买家／商家资料及共用昵称模板编译通过 |
| `python tools/module_versions.py check` | 16个模块登记有效，当前工作区文件均有归属 |
| 三个资料脚本 `node --check`、本轮已跟踪文件 `git diff --check` | 均通过；不代表全站业务验收 |

后端范围：本人有效身份校验、跨账号拒绝、独立保存且不依赖联系方式、角色等额外字段拒绝、重名、修改／清空、30个表情字符、超长与控制字符、无效JSON、HTML样式文本、旧资料PUT兼容、商家昵称不改店名、会话即时读取昵称／同名隔离及买家看到店名。前端覆盖错误重试、重复提交、账号切换、取消、独立PATCH、未启用禁用态、会话标题刷新与文本渲染。

首次MySQL回归暴露表情写入失败；新增列显式utf8mb4后仍需将Django连接从默认utf8改为utf8mb4。迁移DDL另暴露事务限制，通过 `Migration.atomic=False` 修正。最终真实MySQL全部通过。失败建库留下的唯一临时测试库经名称、建库时间、迁移及测试用户核对后清理；未操作业务库。

## 同步main后的精确交付复验

交付分支正常同步 `cf13522` 后，仅整理27个昵称相关文件；未混入其他工作区的Enter发送、聊天布局、采购页、清理或CNY计价实现。重新执行：

- `python .scratch/user-nickname-20261022/delivery_checks.py sqlite`：65项，64通过、1项MySQL专用跳过。
- `python .scratch/user-nickname-20261022/delivery_checks.py mysql`：65项全部通过，随机MySQL隔离测试库正常销毁。
- `python .scratch/user-nickname-20261022/delivery_checks.py check`：系统检查通过、makemigrations无变化、5个模板实际渲染通过、昵称脚本可定位。私有runner从原工作区加载本机环境变量，导入和验证均来自交付Worktree；运行器及凭据不入库。
- `node --test client/tests/profile-nickname.test.js client/tests/engagement-messages.test.js client/tests/engagement.test.js`：**20项通过**。上表26项为实现工作区之前的回归，交付分支不含并行任务的额外6项前端用例，不混算结果。
- `python tools/module_versions.py check`：16模块及文件归属通过；`git diff --check`通过。最终提交及主干SHA、完整Git门禁结果记录在PR正文。

## 浏览器与业务库边界（详细）

- 8873隔离预览使用独立SQLite、专用测试账号及签名密钥。真实页面完成登录、空联系方式单独保存昵称、清空恢复、再次修改、刷新后持久化，并验证商家会话列表和标题显示“春山茶客🍃 · #1”；另一个会话保留独立编号。
- 页面截图与运行日志保存在本机 `.scratch/user-nickname-20261022/`，均为模拟数据；未向真实商家发送咨询或修改真实账号昵称。
- 授权前业务MySQL只读盘点：13个账号，users迁移至0007，新昵称列尚不存在。授权后启用结果见下节。
- 未执行全量系统回归、生产部署或PostgreSQL迁移；用户表实际使用MySQL，PostgreSQL AI存储无本次模型变更。

## 已授权本地启用

用户明确授权备份、应用昵称字段迁移、重启及验证后推送PR。2026-10-22已完成用户表和迁移记录SQL备份，检查建表语句、插入内容、完成标记及文件SHA-256；另保留原有列快照。备份仅存本机忽略目录，无凭据入库。

仅应用 `users.0008_userprofile_nickname` 成功；13个账号原有所有列的数据摘要一致，新列为varchar(30)/utf8mb4、默认空，迁移记录仅新增本目标。8000后端已重启且系统检查无错误；原有AI存储的两项待迁移保持未应用。

真实8000 HTTP验证：买家／商家资料GET、昵称PATCH等值保存空字符串、咨询列表GET及两端资料页／消息页／昵称静态脚本均通过，账号昵称未改变。初次验证脚本误用买家角色字面量buyer及旧GET接口的Bearer格式，修正为实际customer角色及GET原始JWT后通过，产品代码未因此修改。浏览器确认实际买家资料页昵称输入及保存按钮可用。

以下为执行方案留档：

1. 确认8000进程及目标业务库；暂停旧后端，生成用户表及迁移记录备份并检查备份可读、完整，记录原有列数据摘要和用户数，备份只保存在本机私有目录。
2. 执行限定 `python manage.py migrate users 0008_userprofile_nickname --database default`，不执行其他App待迁移内容。
3. 核对用户数量、原有列摘要不变，昵称默认空、新列varchar(30)/utf8mb4、0008已登记。失败停止检查，不自动回退或覆盖业务数据。
4. 启动本地8000后端，检查资料读取、咨询列表及页面路由；真实昵称由本人从个人信息页保存。分别报告备份、迁移、后端和页面验证结果。

依据 `docs/Git协作规范.md` 第5节：“数据库上线和回退须单独授权、备份并制定方案，不自动对业务库执行操作。” 本次已取得昵称迁移的明确授权，未从此前其他迁移授权推导。
