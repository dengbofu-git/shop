# 常驻MCP服务与启动方式

2026-10-29；support_ai 0.26.0、core 0.10.0。沿用[唯一入口规则](../../architecture/agent-data-access.md)，决定见[ADR0010](../../../adr/0010-resident-agent-mcp.md)，结果见[验收](../../evidence/2026-10-29-mcp-resident/verification.md)。本页描述实现，不表示业务已部署。

## 启动与请求分开

服务启动：SDK加载 → 并行启动默认2个 `mcp_agent_worker` → Django初始化并发出就绪帧 → 开放本机HTTP接口。health的ready表示进程池已预热，不表示所有数据库／模型服务正常。

问题到来：宿主认证、幂等和咨询检查 → AgentDataAccess经HTTP初始化本轮MCP Client → SDK验证服务密钥 → 获取空闲进程 → 后端验证并一次性claim签名grant，创建DataSession → MCP工具 → 领域服务读取 → 签名私有结果 → 完成后关闭会话及数据库连接 → 进程回池。正常提问不创建SDK或Django进程。

模型工具结果契约保持不变。仍有少量HTTP往返；模型冷加载、SQL首次连接和宿主首次加载执行图的延迟，不属于进程预热保证。

## 身份和状态

- 官方SDK提供stateless Streamable HTTP。协议无状态不等于业务会话无状态：一轮grant对应独立DataSession及独占进程租约，同轮工具共享既有Retriever和预算状态。
- `Authorization: Bearer <服务密钥>`认证宿主，`X-Tea-Saas-Agent-Grant`传递签名上下文。用户JWT不转发；身份、引用、预算不接受模型自报。服务密钥本身不能授权读取买家数据。
- Worker启动时没有本轮grant，收到open控制帧才创建DataSession。后端逐次复验买家、咨询归属和revision；grant通过stdin传入，不进入进程命令行或全局环境。
- 签名私有输入／输出继续绑定nonce及单调序号；订单导航、预算和后端Trace不进入模型DTO。DELETE `/agent-session`只释放资源，数据始终走 `/mcp`。
- HTTP客户端禁用环境代理和重定向；服务固定绑定127.0.0.1、拒绝浏览器Origin、保留DNS重绑定保护。宿主与Worker仍需访问同一私有目录；跨机器文件交接、TLS、远程身份及最小数据库角色未实现。

## 容量、故障和清理

默认2个进程，参数范围1—16；池满最多等待2秒，返回可重试BACKEND_BUSY，不由请求临时启动进程。宿主生成答案期间仍占租约，不代表高并发容量已验收。

租约不超过后端验证的签名期限，最长120秒。后台每秒监督过期租约和进程故障；过期执行被终止，替换进程在后台预热。旧失败请求不迁移到新进程，不获得新DataSession或重置预算；下一轮必须使用新grant。原40次工具上限、模型预算和Retriever状态保持有效。

正常结束清除本轮DataSession、关闭数据库连接后归还健康进程。关闭通知丢失由到期回收兜底。health暴露available、active_sessions、worker_starts、startup_ms和随机实例标识，不含买家、grant或凭据。worker_starts计数可证明处理多轮时没有重复启动进程。

## 配置

在既有 `.env` 中增加以下内容，不覆盖原数据库／模型配置：

```dotenv
SUPPORT_MCP_TRANSPORT=http
SUPPORT_MCP_URL=http://127.0.0.1:18082/mcp
SUPPORT_MCP_SERVICE_TOKEN=<本机一次生成的随机密钥>
```

密钥为32—256位字母、数字、下划线或短横线，Web和MCP相同。可在本机运行 `python -c "import secrets; print(secrets.token_urlsafe(48))"` 后保存到 `.env`，不要提交或发到聊天／日志。缺失时安全失败，不自动生成临时密钥或降级。

Web与MCP统一使用Python3.13，SDK保持依赖隔离；按实际目录配置，将下列`<仓库根目录>`替换为本机路径，例如：

```dotenv
SUPPORT_MCP_PYTHON=<仓库根目录>/tools/tea_saas_mcp/.venv/Scripts/python.exe
```

使用既有 `tools/tea_saas_mcp/requirements.txt`，不向业务环境安装SDK。本轮没有新增依赖或Migration。

## 一次启动本机开发后端

在已配置好的仓库根目录运行：

```powershell
python manage.py run_support_backend --addrport 127.0.0.1:8000 --mcp-port 18082 --mcp-workers 2
```

启动器先确认自身MCP实例ready，再启动Web，不借用或关闭已有同端口进程。Web使用 `--noreload`，修改代码后重启整个命令；Ctrl+C关闭本次Web和MCP进程树。已有8000／18082服务须由管理者正常停止后再切换，本轮没有操作这些业务进程。

已有独立Web进程管理器时，可单独启动：

```powershell
python manage.py run_agent_mcp --port 18082 --workers 2
```

确认 `http://127.0.0.1:18082/health` ready后再启动Web。多个Web Worker共享此服务，不能每个Worker启动一套池。聊天处理器不会调用启动器。

## 追踪和兼容

常驻请求保留 `mcp.session.connect`、`mcp.initialize`、`mcp.tools.list`、`mcp.rpc`及原后端授权／RAG节点，正常请求不再有SDK或Django spawn／ready节点。会话初始化包含分配及DataSession创建；服务预热耗时由health单独观察。

`SUPPORT_MCP_TRANSPORT=stdio`为显式兼容模式，不作为HTTP失败时自动回退。原开发者stdio公开详情入口保留。HTTP、预览和评测共用AgentDataAccess；测试显式选择合成stdio或真实resident，不能将测试替身当作生产回退。
