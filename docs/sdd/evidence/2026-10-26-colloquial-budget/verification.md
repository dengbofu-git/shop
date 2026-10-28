# 口语金额与预算范围澄清

2026-10-26，support_ai 0.21.1。开发分支codex/orders-merchant-isolation，未提交／推送。既有工作区改动继续保留；前端无本轮增量，因此web不升版。升版前读取到已有其他任务的0.21.0，因此从该版本递增，保留其changelog，不回退至0.20.x。

## 当前事实与范围

- 只读检查当日15:28两轮“推荐400块左右的茶”：均返回通用“暂时无法可靠确认本轮要求”；对应日志为support.planning.unavailable / ValueError，商品查询未执行。历史记录没有更具体的规划诊断，因此无法还原当时的模型输出字段。
- 当前源码币种证据校验不支持“块／块钱／元钱”，而精确总价规则还要求总价等范围词；是可复现的口语支持缺口。本轮补齐币种证据，并为不含其他约束的明确金额问句提供确定性解析。
- 未明确单件／整套时保存CNY400及原话证据，只追问budget_scope。原范围补充保留金额，单价转普通工具并移除组合模式，总价转组合工具并保留near模式；显式新请求不继承旧总价范围。
- 不吞掉排除项、购买数量等额外后缀，不把实物“400块茶饼”交给金额精确规则。需要商品分类校验时延后到条件齐全，澄清时不无条件读分类表。
- 规划失败响应新增无正文的安全diagnostics：阶段、错误类型、Pydantic字段／错误码或白名单原因；不加入原始模型输出、证据输入或用户正文。

## 验证

解释器：E:/miniconda/envs/dadashop/python.exe。

1. `python -X utf8 -m unittest support_ai.test_colloquial_budget -v`：8项通过，模型替身禁止任何规划调用，不接数据库。
2. 首次完整图链路的3项用例：1通过、2失败，定位为normalize_recommendation无条件查询Catalog；修正为澄清先行、仅实际搜索且有硬分类时读取。
3. `python -X utf8 manage.py test support_ai.test_colloquial_budget support_ai.test_colloquial_budget_graph --settings=support_ai.test_settings --noinput -v 2`：11项全部通过，Django检查0问题，default和ai_storage数据库均未使用／未创建。包含截图金额、币种别名、单价／总价下一轮、已有条件保留、未知后缀、伪造币种及失败诊断；完整图使用真实澄清处理器，仅最终商品查询替换为合成空候选。
4. `python tools/module_versions.py check`：16模块文件归属通过；10个相关Python文件AST通过；定向git diff --check及新增文件行尾空白检查通过。

15:43重启本地8000预览，PID8400替换为39532；没有执行迁移。客服页面可用性与实际模型／商品业务验收分别判断。

未运行真实模型、业务商品库查询或浏览器交互验收；不迁移数据库、不改历史对话。首次只读诊断因终端GBK遇到人民币符号报错，随后以-X utf8重读成功，未发生数据库写入。
