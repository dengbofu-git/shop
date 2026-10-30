# 本地功能完整性整合

基线：origin/main `7427489b74adabe5860c6102acff2be485fa2787`。用户授权全工作区核对、移除已审核旧副本并保留功能完整的唯一本地版本；未授权推送或创建PR。

## 已纳入的内容

- main的采购车Redis原子更新、重试幂等、推荐快照归属、有效商家/正价/库存校验、CP-SAT套餐和购买条件证据。
- 本地常驻HTTP MCP、预热Django池、跨进程追踪、SSE；保持订单/库存/支付/账号权限主干实现。
- 人民币默认、商品详情咨询和进店布局、商家洞察两标签、管理监控移除信息按钮；商家助手保持退役。
- `tools/local_closeout.py`分离audit/plan/apply：计划哈希与两个工作区快照绑定，先校验恢复ZIP及历史Migration，再迁回持久主目录；不执行数据库迁移、Git reset/stash、提交或推送。

## 本轮实际验证

| 范围 | 结果 |
| --- | --- |
| Django阶段整合回归 | 690项，637通过、53按条件跳过；仅隔离SQLite和内存缓存 |
| 推荐/套餐、MCP、SSE及运行入口定向 | 65项通过 |
| 推荐采购车真实Redis | 独立临时Redis + SQLite，15项通过；测试容器已停止 |
| 前端行为 | Node共27个测试文件、110项通过；包括人民币默认缓存、流式和加车行为 |
| MCP SDK进程池 | 独立Python3.13 SDK环境，6项通过 |
| 常驻原生协议链路 | 19项检查通过；临时SQLite + SQLite知识库，provider_calls=0，清理完成 |
| 主目录迁移工具 | 17项合成Git仓库场景通过，包括Windows行尾、原始字节恢复、新编辑、计划/备份篡改、暂存意图、链接路径和历史Migration拒绝 |
| 逐资源回收工具 | 6项合成Git仓库场景通过；备份、现场变化、运行占用、主目录/唯一提交、正常移除及失败保留 |

阶段回归跳过项不是通过；真实支付、真实模型质量及生产容量未在本轮重测。恢复包、逐文件SHA256、原始补丁及本机执行日志位于持久主目录`.scratch/git-delivery/unified-20261029/`。

## 本地运行与回收事实

- 已验证的整合源码迁到持久主目录，分支为`codex/core-unified-runtime`。Web、常驻MCP、到期清理及知识Worker均切换为同一主目录；推荐加车接口由404恢复为401鉴权响应。
- 知识Worker旧镜像缺少OR-Tools。官方基础镜像拉取遇镜像源403后，使用已存在且核验为Python3.13的基础镜像安装锁定依赖，生成新镜像；临时容器验证Python3.13.18、Django5.2.18、OR-Tools9.15.6755。默认构建入口仍为仓库Dockerfile；未修改Docker镜像源或业务存储卷。
- 13份历史工作区经逐资源备份核验后正常Git移除，其中2个路径仅剩被进程占用的空目录，Git注册与源码已移除。另1份原工作区通过Codex托管归档完成。所有恢复材料位于持久主目录。
- 本次临时整合区已迁回主目录，但Codex以“当前聊天主工作区不可删除”拒绝归档；没有改用底层删除绕过保护。该目录无运行服务，回收仍为blocked。
- 收尾期间发现其他活动聊天在主目录新增采购车状态和订单模型改动，晚于上述第一轮验证。用户随后明确授权通知“主项目”“前端”“agent设计”暂缓写入并统一复核，三个聊天均已确认暂停。其改动保留并纳入下述第二轮验证，不覆盖已有工作。
- 本地main正常快进到本页基线；旧本地分支仅用`git branch -d`回收，未删除远端对象。没有项目提交、推送、创建PR或Git强制清理。

## 暂停并行写入后的第二轮验证

| 范围 | 实际命令与结果 |
| --- | --- |
| 全模块隔离SQLite及临时Redis | `manage.py test users goods carts orders pays inventory supplier admin_panel engagement support_ai ai_storage tea_saas --settings=support_ai.test_settings --noinput`：707项，669通过、38跳过；包含新清理任务 |
| 实际MySQL8.0.27 + 临时Redis | 同一环境的`orders.test_reservations orders.test_cart_cleanup carts.test_recommendation_cart carts.test_product_names`：57项全部通过，无跳过；覆盖99/50并发预留、事务回滚、重复清理、断连、提交后新增及删除重加；实际执行新增迁移 |
| 最新前端 | Node所有27个测试文件，110项全部通过；补查缺货99件保留、当前50件提示、9到10件及静态缓存标记 |
| 最新原生MCP | `tools/tea_saas_mcp/agent_integration.py --resident`：19项通过，独立SQLite及知识库，provider_calls=0，临时进程清理完成 |
| 归属和结构 | `tools/module_versions.py check`：15模块、工作文件均有归属；`git diff --check`通过 |
| 真实本地服务 | 21项GET检查通过：页面、采购车、订单、商家待办及洞察、咨询列表、评价资格、跨账号/角色拒绝和退役路由；采购车内容摘要不变；两别名Redis PING与MCP两Worker ready |

全模块MySQL曾尝试运行697项，失败106项、跳过22项：104项用户名长度夹具异常、1项name长度异常、1项响应缺少intent_source。日志保留在`final-mysql-tests.log`，**没有将该轮记为通过**；只修正本轮选定的采购车合成账号长度后重新运行57项真实交易检查并通过。其他MySQL夹具和响应差异仍需独立核对，不据SQLite结果声称全模块真实后端验收完成。首次隔离命令受沙箱连接限制、导入路径及静态脚本解码检查失败，修正执行环境后重测，均不计入通过数。

## 用户授权后的本地数据库启用

用户在审核具体范围后明确回复“授权应用并重启”。实际计划只有`orders.0006_cartcleanuptask`，仅新增任务表、约束和索引；未改写历史Migration。

- 迁移前SQL备份1532243字节，SHA256为`da4d538b1f4e26cfe0d16e4b7258322c5c44a61c599c85b7043d4945f613c443`，覆盖66张表、6883行。备份在无业务挂载的独立MySQL8.0.27容器恢复，全部原始列与行摘要一致。
- 停止核验归属的本项目服务后，执行`manage.py migrate orders 0006_cartcleanuptask --database default`，显示OK，目标计划为空。
- 63张原业务表和既有框架类型/权限行摘要不变；Django正常新增1条模型类型和4条权限。新任务表为空，唯一约束、区间约束及两个索引存在。未创建真实测试订单或调用支付/模型。
- 从持久主目录统一重启Web、常驻MCP和30秒到期/采购车清理进程；知识Worker同样挂载主目录。启动记录、备份、恢复结果、迁移结果和只读验收保存在本机忽略目录，凭据及SQL不入库。

该启用是本地开发运行，不代表提交、推送、生产部署或开机自启。
