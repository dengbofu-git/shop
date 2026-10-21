# tea_saas 领域术语入口

当前产品及工程包名称为 `tea_saas`，物理工作区名称以本机实际路径为准。本页整理现有源码和规格中的用语，供任务、文档、代码评审统一引用；不新增业务规则，也不证明现有实现已完成验收。

| 术语 | 本项目含义与边界 | 依据 |
| --- | --- | --- |
| 买家 | 采购商品、使用本人订单与客服入口的产品角色；角色名不替代接口认证和对象归属校验 | [身份域](docs/sdd/catalog.yaml)、[系统边界](docs/sdd/architecture/context.md) |
| 商家／茶企 | 维护商品并使用商家经营入口的产品角色；文档统一称“商家”，代码保留既有 `supplier`、`merchant_ai` 标识 | [平台定位](docs/sdd/modules/platform/tea-saas-platform.md) |
| 平台运营 | 使用运营管理和 Agent 配置入口的产品角色；权限以当前认证与权限契约为准 | [系统边界](docs/sdd/architecture/context.md) |
| SPU／商品系列 | 商品系列，关联品牌、分类及商家；任务涉及具体售价、规格或库存时，应明确到 SKU | [SPU 模型](goods/models.py) |
| 站内咨询 | 买家与商家的人际会话；独立于AI客服，默认不进入模型上下文 | [站内咨询](docs/sdd/modules/merchant-operations/buyer-merchant-conversations.md) |
| 购买后评价 | 绑定一个已完成订单商品项，按购买时商家与SPU公开汇总；不由旧计数或自动好评生成 | [评价规则](docs/sdd/modules/catalog-content/purchase-reviews.md) |
| SKU／商品规格项 | 具体商品项，关联 SPU，具有售价、库存及上架状态；公开详情工具以 `sku_id` 定位 | [SKU 模型](goods/models.py)、[公开详情](support_ai/product_details.py) |
| 采购车／购物车 | 买家待结算的商品选择；产品文案用“采购车”，既有代码和接口保留 `carts` 等标识 | [架构与展示约定](docs/sdd/architecture/context.md) |
| 可用库存 | 必须说明使用入口及来源。当前 AI 公开商品读取有账本时使用账本可用量，无账本时回退 SKU 库存；其他入口存在口径差异 | [公开商品范围](support_ai/recommendations.py)、[已知差异](docs/sdd/architecture/context.md) |
| 展示币种／参考换算 | 当前公开商品工具沿用 USD 展示约定，部分页面提供参考换算；不能据此推断支付或结算币种 | [商品详情限制](support_ai/product_details.py)、[未决问题](docs/sdd/product/open-questions.yaml) |
| 实现模块 | `versions/modules.json` 中有独立版本的代码资产归属，如 `goods`、`support_ai` | [模块清单](versions/modules.json) |
| 业务域／能力切片 | SDD 中的 `MOD-*`／`CAP-*`；业务归属和能力阶段不等于 Django App 划分或实现模块版本 | [SDD 工作约定](docs/sdd/governance/workflow.md) |
| SaaS 定位 | 当前产品定位；不代表已实现租户隔离、订阅计费或完整交易闭环 | [当前状态](docs/sdd/product/current-state.md) |

发生用语冲突时先核对所链接的当前规格与源码；未确认的含义记入相关 CAP 的开放问题，不从名称、Mock 或历史报告推导新规则。业务语义变更仍按现有 SDD 约定评审；架构取舍按 [ADR 约定](docs/adr/README.md)记录。
