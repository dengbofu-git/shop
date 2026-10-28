# 预算口径的受限上下文语义

2026-10-26，support_ai 0.23.0；分支codex/orders-merchant-isolation。升版前保留当前工作区已有0.22.0检索改动及changelog，从实际版本递增；未提交／推送。无Migration或前端增量。

## 改动与边界

- pending推荐且缺budget_scope时，已知短答走规则；其他短答由BudgetScopeDecision结合程序生成的当前问题判断unit／total／uncertain及是否纯范围回答。分类模型不输出金额、币种、商品、数量或工具名；程序沿用已校验的原条件。
- 新金额／币种／茶类／明确新任务直接交完整规划器；分类结果不是纯范围补充也交完整规划器。混合修改中的上下文口径同样由程序建立来源，其余字段仍逐项校验，不能吞掉其他条件。
- 仅required.price_basis的unit／total可带程序context_turn_id。当前解释要求当前有效pending问题、完整本轮原话；历史复验要求原问题、选择轮次、先后顺序及该轮保存的budget_scope_evidence一致。无解释、跨咨询或过窗口均不接受；不以全局开关跳过证据检查。
- 完整规划模型不能生成内部context_turn_id，模型输入剔除该字段及解释记录。金额、币种、分类等字段不享受上下文语义豁免。规则路径兼容旧证据。
- scope阶段默认thinking=disabled、max_tokens=192，通过SUPPORT_SCOPE_THINKING／SUPPORT_SCOPE_MAX_TOKENS配置并共享整轮预算。无效模型结构抛技术错误，不写成功轮次或把问题说成用户缺少说明；uncertain仅复问已知金额对应的范围。

## 隔离及模拟提供商验证

`python -X utf8 manage.py test support_ai.test_budget_scope_semantics support_ai.test_colloquial_budget support_ai.test_colloquial_budget_graph support_ai.test_total_budget_generic_tea support_ai.test_cost_control --settings=support_ai.test_settings --noinput -v 1`

最终代码在补充模型输入元数据剔除后再次运行，50项全部通过，Django检查0问题；隔离SQLite、模拟模型／HTTP，不连接业务库或真实模型。覆盖非字面短答接受、金额币种保留、否定和不确定、新任务及新金额不忽略、混合修改、保存后再改预算、缺来源／跨咨询拒绝、原规则回归和scope提供商实际请求192-token／关闭thinking／共享预算。见[最终测试日志](final-tests.log)。

## 已授权真实模型合成验证

用户本轮明确允许6条新编短答，只发送虚构3000元问题，不发送真实历史、偏好或商品。当前有效模型为deepseek-flash；脚本禁止完整规划器的额外提供商调用，最多6次，每次最多192输出Token，无自动SDK重试。

6/6通过：总的→total；全部加起来→total；后一种→total；一件的→unit；都可以→uncertain；不是每件，是全部算在一起→total。金额均保留3000.00。实际6次scope调用，输入3022／输出301 Token，无未知用量、拒绝或超限。模型结果又经过当前语义规划及来源合并校验，不是直接把模型JSON当商品结果。

详见[合成结果](real-model.json)。该小样本不代表生产准确率、全部语言或完整推荐质量通过；未将真实客户历史发给模型。

## 本地服务

首次真实测试在读取运行配置时遇MySQL拒绝连接，未发模型请求。发现Docker后端已停止，正常start误报已运行；按本会话已授权的Docker恢复范围重新启动进程，仍卡在引擎初始化后，仅重启docker-desktop专用WSL运行环境，不删除发行版、容器、数据卷或操作其他发行版。恢复后启动原3306的master容器，保留restart-policy=no与原数据库配置，未切换其他项目13306实例。随后6条真实合成验证成功。

配置、模型调用权限、隔离验证、本地加载及业务数据库迁移分别记录；本轮不执行数据库迁移或修改旧问答。

8个相关Python文件AST、16模块归属及定向git diff --check通过；仅有既有LF转CRLF提示，不是空白错误。没有将工作区其他未提交任务混入Git交付。

17:33重启本地8000预览，PID40832替换为5412，加载support_ai 0.23.0；启动Django检查0问题，客服HTML只读GET200，原MySQL3306与PostgreSQL5433新连接均成功。当前共享工作区的ai_storage仍有4份未应用迁移，本轮没有执行迁移，也没有把其他检索增量的迁移状态写成已验收。
