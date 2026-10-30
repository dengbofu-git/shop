# tea_saas MCP 与 Skill 接入

日期：2026-10-18。实现范围为仓库级 `tea-saas-change-delivery` Skill 和本地 stdio MCP 的 `get_product_details`。`search_products` 尚处于[详细设计](sdd/modules/ai-support/search-products-design.md)阶段。本增量没有数据库迁移、HTTP MCP 地址、远端部署或模型调用。

2026-10-28补充：用户确认[模型 Agent 数据访问统一经 MCP](sdd/architecture/agent-data-access.md)并要求“运行”。support_ai 0.24.0／core 0.9.0已完成应用入口迁移与隔离验证，见[运行设计](sdd/modules/ai-support/mcp-runtime.md)；原静态差异保存在[清单](sdd/modules/ai-support/mcp-migration.md)。下文安装配置仍适用于独立开发者公开详情工具；它与客服的私有请求授权是两种入口，不能混同。

## 应用客服入口

客服由 Django 宿主创建请求级 MCP Client，签名绑定本人身份、咨询、当前引用及预算，通过独立 SDK 环境访问固定后端命令。商品、组合推荐、解释、订单、本人偏好／历史和知识工具列表见[运行设计](sdd/modules/ai-support/mcp-runtime.md)。不在用户级 Codex MCP 配置里复制买家凭据，也不把私有授权写入工具参数。

服务端配置 `SUPPORT_MCP_PYTHON` 为 SDK Python 3.12绝对路径，默认使用仓库 `tools/tea_saas_mcp/.venv`；Django继续运行在现有3.9环境。调用／整轮超时默认40／120秒。缺配置或 MCP 故障返回明确错误，没有本地查询降级。部署后需要正常重载应用，本轮未操作已有业务服务。

真实协议验收使用业务解释器运行 `python -X utf8 -m tools.tea_saas_mcp.agent_integration`，默认创建临时 SQLite；增加 `--postgres` 验证随机 PostgreSQL 测试库，增加 `--mysql` 使用本机已有 `mysql:8.0.46` 创建唯一标签、随机端口、无挂载的临时容器。真实后端验收命令会创建并清理专用测试资源，不使用业务 MySQL，外部模型调用被关闭。结果及边界见[证据](sdd/evidence/2026-10-28-agent-mcp/verification.md)。

## Skill 使用

技能入口为 [SKILL.md](../.agents/skills/tea-saas-change-delivery/SKILL.md)，随仓库共享，由 Codex 从 `.agents/skills/` 发现。示例：

```text
使用 $tea-saas-change-delivery 实现这次商品查询改动，并完成定向验证。
使用 $tea-saas-change-delivery 仅提交我指定的已有改动。
```

技能读取 `AGENTS.md`、Git 协作规范和模块清单，不复制固定版本；区分 IMPLEMENT 与 DELIVERY_ONLY，并分别判断提交、推送、PR、合入和部署授权。添加技能不会向 LangGraph 自动加载指令，也不会自动提交代码。

## MCP 运行边界

官方 SDK 与 Django 使用两个 Python 环境：

- `tools/tea_saas_mcp/.venv`：使用 Python 3.13，安装单独锁定的 MCP SDK 1.29.1（受支持的 v1 维护线）。
- Django Python 3.13：使用仓库业务依赖，通过固定 `manage.py mcp_product_details` 命令读取商品；SDK的依赖环境独立，Python运行基线保持一致。

本地宿主通过 stdio 调用 MCP，适配器使用宿主配置的绝对 `TEA_SAAS_PYTHON` 路径启动 Django 子进程。工具参数只能提供 `sku_id`，不能指定解释器、命令、设置模块、SQL、用户或文件路径。每次查询启动一个短生命周期进程，避免跨环境安装依赖；这会增加启动开销，应先测量后再决定是否采用常驻只读服务。

本工具采用与买家 Agent 相同的可售范围，只提供已上架且正可用库存的公开商品字段。本地进程继承宿主配置，Django 按既有方式读取 `.env`；MCP 不输出凭据。它属于有本地运行权限的开发者接入，未实现互联网访问认证，不能直接暴露到公共网络。以后增加本人订单或商家数据时，必须另行设计身份绑定及对象授权。

## 安装和配置

在仓库根目录运行；按机器实际位置替换解释器。不要把 MCP 依赖安装到 Django 环境。

```powershell
# 使用 Python 3.12 创建 MCP 环境
python -m venv tools/tea_saas_mcp/.venv
& tools/tea_saas_mcp/.venv/Scripts/python.exe -m pip install -r tools/tea_saas_mcp/requirements.txt
```

若本机 venv 的 ensurepip 不可用，可用已安装的 uv 安装到同一个隔离环境：

```powershell
uv venv --python 3.12 tools/tea_saas_mcp/.venv
uv pip install --python tools/tea_saas_mcp/.venv/Scripts/python.exe -r tools/tea_saas_mcp/requirements.txt
```

将下列配置合并到本地 Codex 配置（路径是新克隆的示例，不代表当前物理工作区或 Conda 环境已改名；必须替换为本机实际绝对路径，不包含凭据）：

```toml
[mcp_servers.tea_saas_catalog]
command = "E:/django/tea_saas/tools/tea_saas_mcp/.venv/Scripts/python.exe"
args = ["E:/django/tea_saas/tools/tea_saas_mcp/server.py"]
cwd = "E:/django/tea_saas"
enabled_tools = ["get_product_details"]
tool_timeout_sec = 35

[mcp_servers.tea_saas_catalog.env]
TEA_SAAS_PYTHON = "E:/miniconda/envs/tea_saas/python.exe"
```

外层工具超时建议大于桥接的 25 秒。加载配置后，通过客户端的 MCP 工具列表确认 `tea_saas-catalog` 及 `get_product_details`。本次实现提供配置示例，不改用户级配置。

## 商品详情契约

输入严格为 `{"sku_id": 123}`，ID 必须为 1 到 2147483647 的 JSON 整数；拒绝布尔值、字符串、浮点数及额外字段。ID 应来自真实目录或用户明确选定的 SKU，不能从商品名称臆造。

成功响应示例（合成数据）：

```json
{
  "schema_version": "1.0",
  "status": "success",
  "data": {
    "sku_id": 123,
    "product_name": "示例绿茶",
    "specification": "50克装",
    "category": "绿茶",
    "price": "12.30",
    "currency": "CNY",
    "price_basis": "unit",
    "currency_source": "configured_base_currency",
    "available_stock": 10,
    "stock_source": "sku_stock_fallback",
    "attributes": []
  },
  "observed_at": "2026-10-18T12:00:00+08:00",
  "limitations": ["基础价格为人民币CNY；外币为参考显示，价格与库存以下单校验为准。"]
}
```

库存存在账本时读取账本 `available_quantity` 合计，仅无账本时回退 `SKU.stock`。库存为零／负数、未上架和不存在统一返回 `status=no_match, data=null`；无匹配是正常结果，MCP `isError=false`。不披露隐藏商品存在性，也不替换成其他商品。

`price` 为两位小数字符串，自2026-10-22按人民币CNY基础价解释，原数值不批量换算。外币仅为参考显示，详见[金额规格](sdd/architecture/currency.md)。`observed_at` 是本次读取时间，不是价格有效期、库存预留或跨查询快照承诺。

公开属性白名单在 `support_ai/product_details.py`，只返回配料、口感、香气、产地、净含量、包装以及明确命名的模拟字段，每次最多 50 条。SPU 与 SKU 层记录均保留，按记录 ID 排序；当前不推断属性覆盖关系。属性值按既有脱敏规则处理。成本价、内部属性、商家身份、仓库明细和客户数据不返回。公开商家文本仍属于不可信数据，不能当成执行指令或已核验认证。

错误响应包含 `status=error, data=null, error_code, retryable`，MCP `isError=true`。桥接使用 `BACKEND_NOT_CONFIGURED`、`BACKEND_TIMEOUT`、`SERVICE_UNAVAILABLE`、`INVALID_BACKEND_RESPONSE`；命令还可返回 `INVALID_ARGUMENT`。SDK 输入校验错误使用 MCP 错误结果文本，不承诺上述业务结构。重试不自动发生。

该查询不调用模型、偏好库或 Redis，不记录会话、足迹、收藏或 OTel。网站 Agent 的对象指代逻辑保留，选定对象后改用同一详情服务；其模型可见属性同步收紧为公开白名单。

## 验证入口

```powershell
python -X utf8 C:/Users/dbf/.codex/skills/.system/skill-creator/scripts/quick_validate.py .agents/skills/tea-saas-change-delivery
& E:/miniconda/envs/tea_saas/python.exe manage.py test support_ai.test_product_details support_ai.test_planning --settings=support_ai.test_settings --noinput
& tools/tea_saas_mcp/.venv/Scripts/python.exe -m unittest tools.tea_saas_mcp.test_server -v
python tools/module_versions.py check
git diff --check
```

Django 定向测试使用隔离 SQLite，不验证真实 MySQL 聚合语义。MCP 测试覆盖 SDK 协议、固定命令派发、错误及超时回收；合成协议测试不代表已接入用户当前客户端或真实商品库。[本次验证记录](sdd/evidence/2026-10-18-mcp-skill/verification.md)分别列出通过项与已有失败。

需要验证 SDK → 子进程 → Django → 合成数据库完整链路时，在 MCP 测试前设置 `TEA_SAAS_TEST_PYTHON` 为现有业务解释器的绝对路径；测试自行创建临时 SQLite 并在结束时清理，不使用业务库。

## 参考

- [Codex MCP 配置](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [仓库 Skill 发现](https://learn.chatgpt.com/docs/build-skills)
- [官方 MCP Python SDK v1 维护线](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x)
