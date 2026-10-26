# Grounding交付分支验证

日期：2026-10-26。用户授权提交并创建PR，按DELIVERY_ONLY交付本聊天已有实现与评测。原工作区含大量其他模块未提交变更，故在干净独立工作树提取本次增量，原工作区现场保留。

## 基线与合并范围

目标main，源分支codex/support-ai-grounding；基线origin/main为184e2f7113fd45a8d3db89a39dd553427290ef97。最终源SHA、同步main SHA和Git门禁结果记录在PR正文。

主干已有人民币与订单上下文测试修复，交付时保留这些修复和新增订单用例，合并本次KnowledgeDraft/GroundingReview测试替身及输出约束断言。只处理含义明确的测试重叠，没有扩展业务实现或带入其他任务代码。其他模块版本保持main，support_ai为0.19.0，changelog和版本说明同步。

Grounding生产实现与真实模型实测版本的对比见[live-source-comparison.json](live-source-comparison.json)：grounding、business_grounding、tea_explanation、workflow和tool_services逐字节相同；model_client只存在CRLF/LF差别。因此保留先前22场景、28次真实模型请求的原始观察，不重复付费调用。完整[真实模型报告](../2026-10-26-support-grounding-live/verification.md)继续区分规则拦截、模型判断和合成工具边界。

## 本次实际验证

全部命令的解释器标记python均指本机项目Python3.9.25，不复制私有环境文件；执行环境显式提供合成配置，default/ai_storage为隔离SQLite内存库、LocMem缓存，没有连接业务库或模型。命令和结果见[commands.json](commands.json)。

| 命令 | 结果 |
| --- | --- |
| `python manage.py check --settings=support_ai.test_settings` | 通过，0个系统问题 |
| `python manage.py test support_ai --settings=support_ai.test_settings --noinput -v 2` | 162项全部通过，见[support-regression.log](support-regression.log) |
| `python tools/module_versions.py check` | 通过，16模块均有归属 |
| `git diff --check` | 通过 |
| `python -m unittest tools.tests.test_project_identity tools.tests.test_module_versions -v` | 路径显示规范化后6项通过，见[governance-tests.log](governance-tests.log) |
| `python -m unittest discover -s tools/tests -p test_git_policy.py -v` | 23项通过，见[git-policy-tests.log](git-policy-tests.log) |

原工作区较旧基线上的4失败/1错误仍保留在历史记录中，没有将它们改写为历史通过；当前交付测试在最新main修复基础上重新执行。此次没有新增Migration或前端运行代码，不包含数据库上线、浏览器端到端、全项目业务验收或部署。

## 发布记录规范化

首次命名回归在5份新证据中发现物理工作区/解释器名称触发既有退役命名规则。没有修改检查器或添加例外，仅将交付副本中的本机绝对路径显示为`<workspace>`、`<project-runtime>`或`python`；失败、数值、原始模型回答和冻结输入均未改写。原工作区文件及额外原字节备份保持不变，原始与发布指纹见[publication-manifest.json](publication-manifest.json)。重新验证使用相同命名门禁。

Git对文本的CRLF/LF转换不改变语义。实时模型批次的工作副本哈希原样保留；交付时另保存证据的Git内容哈希/对象绑定，供跨平台复核，不把工作副本字节哈希和Git规范文本哈希混为同一个值。

全部历史测试及真实模型记录的原工作副本、发布副本与预期LF/Git对象指纹见[evidence-content-manifest.json](evidence-content-manifest.json)。发布副本保留原先的模型答案和统计；路径展示变化由publication-manifest单独解释。

暂存门禁另外识别出Windows日志中的重复CR换行和统一补丁空白上下文。日志仅转换换行；原始补丁无损放入task-patch.json的patch字符串，恢复UTF-8字节后原SHA256一致。发布格式变化及前后指纹见[text-layout-manifest.json](text-layout-manifest.json)，未关闭或放宽任何Git检查。
