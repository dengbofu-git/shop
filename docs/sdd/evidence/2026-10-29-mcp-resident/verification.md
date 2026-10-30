# 常驻MCP实现验收

日期：2026-10-29。分支 `codex/support-ai-mcp`，基线 `c5b09f7d5ac3c5bd124028a8d4a870f438fce389` 上的未提交增量，包含上一轮0.25.0追踪工作；当前support_ai 0.26.0、core 0.10.0。没有提交、推送、业务迁移、部署或重启已有服务。设计见[常驻服务](../../modules/ai-support/mcp-resident.md)与[ADR0010](../../../adr/0010-resident-agent-mcp.md)。

## 实际验证

业务解释器使用既有Python3.9，SDK使用独立Python3.12。测试启动器只把本机配置传给子进程，不打印或保存实际凭据。随机服务密钥仅用于临时验收；没有写入业务.env。

| 命令／验证 | 实际结果 |
| --- | --- |
| `python -X utf8 -u manage.py test support_ai --settings=support_ai.test_settings --noinput -v 1` | 最终278项通过，22.219秒；隔离SQLite和合成模型；覆盖HTTP客户端不启动进程、不降级数据库、秘密头不进入工具参数、统一启动先ready后Web及失败收尾，以及全部既有客服回归 |
| 独立SDK `python -X utf8 -u -m unittest tools.tea_saas_mcp.test_resident tools.tea_saas_mcp.test_server -v` | 19项中18通过、1条件跳过，3.504秒；常驻协议与服务密钥、Origin拒绝、独占租约、满池、进程复用、故障监督、期限回收、旧请求不迁移，以及原stdio兼容。旧可选端到端用例未设置TEA_SAAS_TEST_PYTHON；下行真实链路另行覆盖 |
| `python -X utf8 -u -m tools.tea_saas_mcp.agent_integration --postgres --resident --profile-output .scratch/mcp-resident/profile-first.json` | 19项通过；临时SQLite＋随机PostgreSQL测试库；真实HTTP SDK与Django预热池，模拟Embedding不可用时仍保留关键词证据并标注故障，不做健康负缓存 |
| `python -X utf8 -u -m tools.tea_saas_mcp.agent_integration --mysql --postgres --resident --local-models --profile-output .scratch/mcp-resident/profile-final.json` | 最终19项通过；唯一标签、随机端口、无业务挂载的MySQL8.0.46容器＋随机PostgreSQL测试库；真实HTTP MCP、签名文件、所有数据工具、HTTP／Preview入口、幂等、两买家并发偏好隔离和关闭后旧grant重放拒绝；资源清理完成 |
| 最终health断言 | workers=2、available=2、active_sessions=0、worker_starts=2；处理全部轮次后仍只启动了最初两个Worker |
| `python tools/module_versions.py check`、`git diff --check`、变更Python AST | 16模块归属／版本及空白检查通过，27个Python文件语法通过；不以语法替代真实链路验收 |

最终全量测试已覆盖新增启动器。SDK随后新增的worker_starts健康计数由最终真实链路直接断言；没有因该观测字段重复执行无关测试。原始本机日志位于忽略目录 `.scratch/mcp-resident/`，共享摘要见[measurements.json](measurements.json)，当前源码指纹见[implementation-files.json](implementation-files.json)。

## 最终性能样本

每次请求使用新grant、新DataSession；服务和两个Django进程在请求之前已就绪。两次新请求各执行相同知识查询两次，第二次为同会话证据缓存命中。仅4条合成知识、其中2条可见，存储向量为合成1024维，查询调用本机bge-m3及重排服务；没有外部问答模型调用，不是检索质量或容量评测。

| 阶段，毫秒 | 请求1 | 请求2 |
| --- | ---: | ---: |
| MCP会话连接，含初始化／工具发现 | 45.420 | 34.750 |
| 首次知识查询 | 626.220 | 527.005 |
| 两次Embedding合计 | 157.277 | 153.103 |
| 重排，2候选 | 262.739 | 198.179 |
| 同会话重复查询 | 68.911 | 94.669 |
| 根Trace，两次查询及关闭 | 702.131 | 627.031 |

两Worker预热1750毫秒记录在服务health，不在问答Trace中；该数字不包括SDK自身的Python导入、启动器和Web初始化。请求中没有mcp.sdk.spawn／mcp.backend.spawn／mcp.backend.ready节点，且worker_starts保持2，证明进程启动移出问题路径。

与上一轮[stdio测量](../2026-10-29-mcp-timing/verification.md)相比，原首次查询约4.29—5.42秒、启动链路约3.71—4.80秒；本组首次查询约0.53—0.63秒。两组在不同时间运行，模型服务和系统负载没有严格控制，不能作为稳定百分比、P95或SLA承诺。

另一次本机模型对照中，进程已常驻但首轮Embedding仍耗时3169毫秒；该请求总计约3.69秒。说明模型服务的首次执行／加载或排队仍是独立因素，不能把Python进程预热等同全部模型预热。原业务请求37.689秒未被重放，旧Trace也不能补齐。

## 交付与限制

默认传输已改HTTP，启用此版本前需要共享服务密钥并先启动MCP；未配置时返回明确错误，不透明回到stdio或直接数据库。统一开发启动命令已实现及验证启动顺序，但本轮没有运行它替换已有8000服务。

仅本机loopback及同机私有目录，未验收远程TLS／OAuth、跨主机交接、OS级无数据库凭据隔离、生产多Web进程容量或数据库规模。独占租约在宿主生成回答期间仍占进程。正常命令退出有监督清理；强制终止整套管理器仍应由部署环境管理进程树。没有修改商品、订单、长期偏好、知识ACL或模型业务规则。
