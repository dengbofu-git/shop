# 客服流式反馈验收

日期：2026-10-29。分支 `codex/support-ai-mcp`，基线 `c5b09f7d5ac3c5bd124028a8d4a870f438fce389` 的未提交增量；保留既有MCP追踪／常驻服务工作。本轮模块为 support_ai 0.27.0、core 0.10.1、web 0.33.0。设计见[流式反馈](../../modules/ai-support/streaming.md)。

## 实际验证

解释器使用既有 Python3.9，配置仅传入进程，不打印凭据；Django数据库由 `support_ai.test_settings` 覆盖为隔离SQLite内存库，测试不访问业务数据库、外部模型或真实买家内容。模型 SSE 用 httpx.MockTransport 构造，仍走真实 OpenAI SDK 和 LangChain 解析及预算记账。

| 命令／检查 | 本次结果 |
| --- | --- |
| `python -X utf8 manage.py test support_ai tea_saas.test_runtime_logging tea_saas.test_stream_logging --settings=support_ai.test_settings --noinput -v 1` | 最终318项通过，29.967秒；既有客服回归及新流式、模型用量、日志测试，包含LiveServer，以及完整知识MCP图只发布核验文本、复核失败不泄露草稿且不保存轮次 |
| `python -X utf8 manage.py test support_ai.test_streaming tea_saas.test_stream_logging --settings=support_ai.test_settings --noinput -v 2` | 15项通过，8.185秒；补充真实本地HTTP LiveServer测试：提交函数被测试屏障暂挂时，客户端已收到 accepted 帧且数据库尚无新轮次；释放后收到 done，再用 JSON 协议重放同一请求，最终仍仅一轮 |
| `node --test tools/tests/test_support_stream.cjs` | 10项通过；逐字节UTF-8／Emoji、CRLF边界、提前进度／任务文本、EOF无done、流内409、前置401、旧JSON兼容、身份变化、超限及异常终止数据 |
| Django `render_to_string('buyer_support.html')` | 真实模板与include解析通过，渲染结果用于浏览器验收 |
| `node tools/tests/support_stream_browser.cjs .scratch/streaming/buyer-support.html` | 已安装Edge无头浏览器通过；5次合成请求验证完成前可见进度和核验文本、done前不标记保存且不显示来源、断线清除临时回答并保留请求ID重试、流内503清除临时回答、账号切换取消并清除旧内容。无页面JS异常；所有非临时本地服务地址均拦截 |
| 两个前端JS `node --check` | 通过；不以语法代替以上行为验收 |
| `python tools/module_versions.py check`、`git diff --check` | 16模块归属／版本和空白检查通过；未运行要求干净工作区的推送门禁，本轮没有交付授权 |

完整本机输出位于忽略目录 `.scratch/streaming/`，不交付配置或真实内容。浏览器验收需设置 NODE_PATH 使其能找到已安装的 Playwright，默认使用已安装的msedge；`SUPPORT_TEST_BROWSER`可指定其他已安装channel。模板渲染与HTTP测试不要求常驻真实MCP在线。

## 结果与边界

- 客户端不再等整轮完成后才收到HTTP内容；先收到处理进度，多任务可先显示已核验任务。固定欢迎和历史重放也有完整SSE结束事件。
- 知识回答仍经独立核验；未通过核验的草稿不进入流。模拟提供商的分片工具调用成功解析为原schema，Token用量40／10保持准确，预算逻辑未移除。
- 连接中断只在取消检查点阻止后续处理；已经发出的远程调用不保证立刻中止，提交中的事务可能完成，依靠请求幂等重放处理未确认状态。
- 没有调用真实DeepSeek，也没有把新代码部署到当前8000业务服务；没有修改原持久主工作区、业务环境文件或重启服务。真实模型延迟、业务MySQL／PostgreSQL并发流、其他ASGI部署及线上反向代理未在本轮验收。
- 本轮没有新增Migration；未执行提交、推送、创建或合入PR。
