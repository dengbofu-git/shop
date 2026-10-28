# 套餐规划服务异常修正（0.25.1）

2026-10-28，截图原话“推荐总价3000块的商品套餐”。本轮为已授权修正的连续故障排查。

## 证据与修复

- 14:43历史错误：旧Web进程与新MCP契约不一致，日志extra_forbidden，模型调用0。14:45通过受管启动器核对身份并重启。
- 14:51重试：服务日志trace 7bb1e3e770b39bd5b2a7092b29b033e2，semantic_planning.py证据修复后再次校验失败被包装RuntimeError，HTTP503。日志不保存原模型内容，因此不能确定该次模型字段值。
- 无历史、无偏好、无业务数据的真实模型复现同一句话，失败链为RuntimeError → IntentEvidenceError(required.budget_mode, unsupported_evidence)，实际2调用（规划1、证据修复1），input5328/output499。最初一次探针误用隔离测试假密钥被401拒绝，不计入成功模型调用或质量统计，已纠正配置。
- 代码检查确认默认cap只在部分new_request路径规范化，澄清动作可绕过；现在统一在所有规划动作下规范化合法本轮来源的默认cap及unspecified／clarify标记证据，保留金额和购买规模缺项。伪造历史／记忆来源仍交严格校验。
- 修复输出格式错误、无关字段或重复证据不足时，返回字段级IntentEvidenceError供澄清，不再包装成技术RuntimeError；网络、超时等技术异常保留原故障语义。

## 实际结果

修复后同一无历史原话真实模型规划成功：source=model，action=new_request，预算3000.00/CNY/total，budget_mode=null，composition=unspecified，quantity_policy=clarify，缺项category与purchase_quantity；返回询问商品类型、套餐款数／每款件数或是否允许按预算自动配量的具体问题。实际仅planning1调用，input4291/output406，未知usage0，未读写业务数据、未提交聊天。两次单样本不作为准确率或成本改进统计。

隔离SQLite及合成MCP回归97项通过；命令与前次verification.md相同，新增澄清动作默认cap及未确定标记证据回归，修复拒绝仍不可篡改金额。输出保存在本机.scratch/bundle-intent-fix-20261028/followup-tests.log。git diff --check通过。

使用本地登记的预览启动器重启加载修复，不迁移数据库、不修改历史对话、不提交或推送。真实模型验证到语义规划及工具分支校验，未冒充经过浏览器认证的完整聊天验收。
