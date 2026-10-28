# tea_saas 商品搜索 MCP 设计草案

规格0.2.0，2026-10-23。search_products尚未实现，目标契约待技术评审；本文件完整替换旧USD限定草案，不保留另一版规格。金额执行[人民币规格](../../architecture/currency.md)，依赖和部分成功执行[Agent规则](current-agent.md)。本次不因修订设计而注册新工具。

## 目标和范围

2026-10-28补充：[统一 MCP 规范](../../architecture/agent-data-access.md)已确认模型 Agent 数据入口；站内推荐应经 MCP 调用本页描述的确定性服务，不再直接调用查询函数。本页仍只是平铺搜索工具草案，未覆盖分组、总价组合、偏好及历史的完整迁移，见[全项目清单](mcp-migration.md)。

向本地 MCP 客户端提供可解释、可核对的公开在售商品搜索，并让现有 LangGraph 推荐工具复用相同的确定性筛选服务。只搜索真实业务商品，不调用语言模型或向量检索，不写入会话、足迹、偏好或采购车。

首版采用最多 4 件的平铺搜索，与 `match_products` 当前上限保持一致；分组推荐继续留在现有编排层。暂不增加任意排序、模糊语义属性、分页游标、总预算分配、实时汇率或个性化长期记忆。只公开本地 stdio 工具，不扩大为远程认证接口。

可观察目标是：硬条件不被放宽，无匹配不被替换，条件回显可核对，结果中的 SKU 可交给 `get_product_details` 实时复查，错误不会伪装成无匹配。

## 与现有实现的关系

| 现有位置 | 可复用部分 | 需要新增或调整的部分 |
| --- | --- | --- |
| `support_ai/contracts.py` | 金额格式、条件数量限制及类型校验 | 独立的结构化搜索 DTO，不能要求外部客户端伪造内部 evidence |
| `support_ai/recommendations.py` | 可售范围、分类别名、硬条件／排除筛选和固定排序 | 将纯查询和回复文字分离，返回有效条件及匹配依据 |
| `support_ai/tool_services.py` | 用户原话证据验证、历史主题、显式偏好来源验证 | 保留在站内推荐适配层，验证后调用搜索服务 |
| `support_ai/product_details.py` | 公开字段、属性白名单、库存和币种说明 | 提取共用公开摘要序列化，避免逐条详情 N+1 查询 |
| `tools/tea_saas_mcp/server.py` | 官方 SDK、stdio、固定命令、错误和超时 | 新注册工具及固定搜索命令；用户参数仍不能控制命令路径 |

MCP 的结构化输入是本次查询条件，不是“用户原话已核验”的证据。站内 Agent 的原文 evidence 校验继续生效。外部客户端若需要自然语言理解，自行完成澄清和抽取，服务端仍对金额、类型、别名、范围和冲突做确定性验证。不能把客户端传来的 `source=MEMORY` 当作用户授权或本人记忆。

## 输入契约

顶层 `additionalProperties=false`，所有嵌套对象同样禁止额外字段。`schema_version` 首版只接受 `1.0`，省略时使用 `1.0`。输入不接受 `user_id`、`merchant_id`、SQL、ORM 字段、工具名、自由表达式、历史记录或任意自然语言指令。

```json
{
  "schema_version": "1.0",
  "required": {
    "categories": ["black tea"],
    "brands": [],
    "keywords": [],
    "price_min": null,
    "price_max": "15.00",
    "currency": "CNY",
    "price_basis": "unit"
  },
  "preferred": {"categories": [], "brands": [], "keywords": ["礼盒"]},
  "excluded": {"categories": ["绿茶"], "brands": [], "keywords": []},
  "limit": 2
}
```

| 字段 | 首版约束 | 默认行为 |
| --- | --- | --- |
| `required/preferred/excluded` | 对象，可省略；不接受 null | 空对象 |
| `categories` | 严格字符串数组，最多 12 项，每项去首尾空格后 1—40 字 | 无分类筛选 |
| `brands/keywords` | 严格字符串数组，各最多 10 项，每项 1—40 字 | 无对应筛选 |
| `price_min/price_max` | 非负十进制字符串或 null，最多 8 位整数和 2 位小数；下限不大于上限 | 无价格区间 |
| `currency` | CNY或共用配置支持的参考币种；明确外币保留原条件并确定性换算 | 省略为CNY，不声称用户明确指定 |
| `price_basis` | 提供价格条件时必须显式提供 unit | 不接受 total／unknown 用作单价筛选 |
| `limit` | 严格 JSON 整数，1—4；布尔值不算整数 | 4 |

`preferred/excluded` 不接受价格、币种和单位字段。文本拒绝控制字符、现有规则能识别的个人信息与空字符串；原始输入 JSON 总长度建议不超过 16 KiB，数组数量在去重前校验，防止以重复项绕过预算。

无筛选参数表示浏览当前可售商品，按固定默认排序返回。未知品牌和关键词属于有效查询，可能无匹配；未知 required 分类返回 `needs_clarification`，避免把拼写或分类层级问题静默变成零结果。preferred 中未知分类同样返回澄清，避免无声忽略偏好。

## 规范化与筛选语义

1. 严格校验类型、大小、金额范围和参数白名单。用Decimal和人民币整数分校验／筛选；外币输入按共用配置换算，记录原值、比例及边界取整，未知币种澄清，不用浮点。
2. 去除文本两端空格并稳定去重。仅复用现有六类中英分类别名；输出原条件与规范化条件，标记 `black tea → 红茶` 等转换。品牌使用数据库完整名称大小写无关匹配，不自动扩展品牌别名。
3. `茶／茶叶／商品／tea／products` 作为范围词，仅在 required 分类中移除并给出说明；excluded 中出现范围词返回澄清，避免无意排除整个目录。不得将“岩茶”自动扩成“乌龙茶”。
4. 分类与品牌各自数组内部为 OR，不同字段之间为 AND；required 关键词逐项 AND，每个关键词在 SKU 名或 SPU 名中命中即可。只进行字面匹配，不解释 `%`、下划线或输入中的 SQL。
5. excluded 任一项命中即排除；不放宽价格、品牌、分类或关键词。required 与 excluded 同分类／品牌交集在规范化后返回澄清；相同关键词同时 required／excluded 同样澄清。preferred 与 excluded 冲突时排除优先，回显冲突偏好已不参与评分。
6. 查询范围调用 `available_products()`：已上架，有库存账本则使用账本可用量合计，仅无账本时回退 SKU.stock，最终要求正库存。不在搜索中顺带修全站库存口径。
7. 对所有满足硬条件的商品评分、排序、截取。偏好只影响排序，不成为硬筛选。

`no_match` 只能表示有效条件下没有满足条件的可售商品。分类无法识别、不支持的币种、总预算或矛盾条件均属于澄清；数据库异常属于 error。

## 排序和匹配解释

首版保持现有确定性排序：偏好分降序 → `is_recommended` 降序 → `sales` 降序 → SKU ID 升序。分类偏好任一匹配加 3 分，品牌偏好任一匹配加 3 分，每个匹配的偏好关键词加 1 分；重复项先去重，不重复加分。

返回 `ranking_version=buyer_catalog_v1`，每件商品返回实际命中的条件键，例如 `required.categories`、`required.price_max`、`preferred.keywords`，并区分筛选依据与排序依据。不把排序分当作购买概率，不从销量推导功效或质量。偏好分不改变硬条件满足情况。

搜索 DTO 不直接公开现有 `product_cards` 的所有字段。公开摘要仅包含 SKU ID、脱敏名称、规格、分类、品牌、两位小数价格、CNY基础金额与可选外币参考显示、单价单位、可用库存、库存来源、固定站内详情路径和实际匹配依据。不返回成本、商家身份、仓库分布、内部属性或历史偏好记录。

## 输出契约

```json
{
  "schema_version": "1.0",
  "status": "success",
  "ranking_version": "buyer_catalog_v1",
  "query": {
    "effective_required": {"categories": ["红茶"], "price_max": "15.00", "currency": "CNY", "price_basis": "unit"},
    "effective_preferred": {"keywords": ["礼盒"]},
    "effective_excluded": {"categories": ["绿茶"]},
    "normalizations": [{"field": "required.categories", "from": "black tea", "to": "红茶"}]
  },
  "products": [{
    "sku_id": 123,
    "product_name": "示例红茶礼盒",
    "specification": "50克装",
    "category": "红茶",
    "brand": "示例品牌",
    "price": "12.30",
    "currency": "CNY",
    "price_basis": "unit",
    "currency_source": "shared_cny_base_config",
    "available_stock": 10,
    "stock_source": "sku_stock_fallback",
    "detail_path": "/product_details.html?skuid=123",
    "matched_required": ["required.categories", "required.price_max"],
    "matched_preferred": ["preferred.keywords"]
  }],
  "returned_count": 1,
  "limit": 2,
  "observed_at": "2026-10-18T12:00:00+08:00",
  "limitations": ["CNY为基础金额，外币仅参考显示；库存未预留。"]
}
```

示例采用稀疏 query 展示，正式 DTO 应对每组条件统一输出全部已定义字段及空值，便于机器比较。`returned_count` 仅是返回数量，不表示总命中量，不增加昂贵的总数 COUNT。首版没有分页，limit 小于总命中数时也不声称结果完整。

| 状态 | products | MCP isError | 行为 |
| --- | --- | --- | --- |
| success | 1—limit 件 | false | 允许不足 limit，说明实际返回数，不凑数 |
| no_match | 空数组 | false | 保留有效条件，不自动扩大范围 |
| needs_clarification | 空数组 | false | 返回明确 reason_code 和需要确认的字段，不执行商品查询 |
| error | 空数组 | true | 返回固定 error_code 和 retryable，不输出底层异常 |

澄清码建议：`UNSUPPORTED_CURRENCY`、`UNIT_PRICE_REQUIRED`、`UNKNOWN_CATEGORY`、`CONFLICTING_FILTERS`。超长输入、额外字段、非法类型／金额格式返回 `INVALID_ARGUMENT`；基础设施错误复用 `BACKEND_NOT_CONFIGURED`、`BACKEND_TIMEOUT`、`SERVICE_UNAVAILABLE`。

澄清前可能需要读取分类字典，所谓“不执行商品查询”不承诺完全不访问数据库。目录字典失败不能当成未知分类。搜索不读取偏好库，客户端 preferred 只表示当次显式排序条件；未来接本人偏好需新增认证服务上下文，不接受自报 owner。

## 服务和适配实现

建议新增 `support_ai/catalog_search.py`，提供 `search_products(validated_query)`。Pydantic 负责严格 DTO 校验，服务负责规范化、分类存在性、确定性查询和公开结果；业务错误使用有限枚举。站内 adapter 先校验推荐 evidence，再转换为 Query DTO；避免让通用搜索服务依赖聊天历史、模型对象或 request。

建议新增固定管理命令 `mcp_search_products`，从 stdin 读取不超过 16 KiB 的 JSON，避免将完整文本放到命令行。MCP sidecar 只向这个固定命令传 JSON；不拼接 shell 命令，不允许客户端指定 settings 或可执行文件。每次仍由当前宿主配置决定数据库，工具数据不能改变连接目标。

SDK inputSchema 和应用 DTO 应从同一契约导出，并增加一致性测试，避免两处约束漂移。MCP 输出提供 outputSchema，同时兼容 content JSON 和 structuredContent。搜索超时沿用桥接 25 秒、客户端建议 35 秒；进程取消或超时后回收子进程，无后台遗留重试。

站内改造采用兼容方式：保持现有 `recommendation_status`、推荐卡片和无匹配文案外壳，由 adapter 翻译新服务输出。站内chat按任务依赖处理偏好故障：普通推荐可提示未使用偏好，明确按保存偏好推荐必须可靠读取；部分完成与幂等遵循Agent和订单目标契约。当前共享入口仍待实施依赖隔离。分组推荐仍逐类使用固定预算，输出顺序与依赖由现有编排管理。首版 MCP 不注册 `recommend_products` 或任何可写工具。

## 性能和观测

分类规范化最多一次字典读取；商品筛选、库存聚合、评分和截取尽量一次 ORM 查询完成。无分页／总数；不要对每件结果再调用 `get_product_details`。MySQL 集成阶段检查 EXPLAIN 和聚合结果，特别是多个仓库与多条件组合时的重复 JOIN 问题。

默认不缓存价格和库存。记录工具名、状态码、耗时和返回数量即可；不把条件原文、品牌关键词、用户信息或 SQL 参数写入观测。若以后接 OTel，应单独定义保留期和写入边界，届时不能继续声称整个工具无持久化写入。

性能验收分别记录冷启动、热调用、Django 启动和数据库查询耗时，并与同条件站内直接调用比较。先测量再设延迟阈值；不预设 MCP 能加速推荐，不把增加网络层当成质量提升。

## 验收矩阵

| 场景 | 必须成立的结果 |
| --- | --- |
| 空条件及固定排序 | 返回最多 4 件可售商品；排序在相同数据下稳定 |
| 两款红茶 CNY 单价不超过 15 | 分类、价格、数量均满足；不足两款不扩大预算 |
| black tea 别名 | 规范为红茶，并回显转换 |
| OR 分类加 AND 关键词 | 只接受定义的组合语义，实际匹配依据可核查 |
| required 与 excluded 冲突 | 澄清，不执行商品查询 |
| 总预算100或未知币种 | 总预算转独立组合任务或澄清，不当作单价；未知币种澄清 |
| 省略币种／明确支持的外币 | 默认CNY／按配置参考换算，保留原条件并回显，结果不得越过硬边界 |
| 未知分类和未知品牌 | 分类澄清；品牌合法查询可 no_match |
| 缺货账本加正 SKU.stock | 不返回该 SKU；无账本时才允许旧字段回退 |
| 偏好与排除冲突 | 排除优先，条件回显说明偏好不参与 |
| 价格／库存／上下架在两次调用间变化 | 第二次重新查询；详情复查能反映新事实 |
| 布尔 limit、浮点金额、额外 ORM 字段、超长 JSON | 参数错误，不能进入查询或派发其他命令 |
| 数据库故障、子进程超时、请求取消 | error 与无匹配区分；子进程回收，无底层异常泄露 |
| 商品名称或属性包含指令／个人信息 | 返回受控脱敏数据；不能触发额外工具或泄露内部字段 |
| 现有买家推荐、多轮和分组场景 | 兼容原 API 外壳，硬条件证据验证不退化 |

验证分层：纯 DTO 与规范化测试；SQLite 合成数据下的应用服务测试；官方 SDK 协议测试；隔离真实 MySQL 聚合测试；最后以合成场景比较站内与 MCP 的筛选结果。真实模型回放单独授权，不作为本次确定性搜索测试的默认步骤。

## 实施顺序和回滚

1. 确认首版平铺 1—4 件、CNY基础金额与可选外币参考显示、公开字段及分类规则，补正式输入／输出 schema 与验收用例。
2. 提取纯搜索服务，先保留旧站内路径，用合成固定数据比较新旧查询结果。
3. 迁移站内 adapter，验证 evidence、软偏好、分组和空结果行为，按真实差异升版 `support_ai`。
4. 增加固定 JSON 命令和 MCP 工具，验证协议与取消回收；升版 `core`，更新两模块 changelog。
5. 完成隔离 MySQL 验证后再配置本地客户端；远程接入、上线及新数据权限分别处理。

无数据库模型变化时不新增 Migration。回滚优先关闭客户端的 search_products 工具，再恢复站内 adapter 的上一实现；保留 get_product_details 和现有 Skill。每步按实际 Diff 判断回滚范围，避免覆盖同分支其他工作。
