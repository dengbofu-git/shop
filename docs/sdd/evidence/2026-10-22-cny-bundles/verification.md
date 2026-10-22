# 人民币基础计价与总价组合推荐交付验证

日期：2026-10-22。范围：总价推荐＋人民币统一；不包含其他工作区未提交的商品目录、商家收藏、经营看板、资源清理或菜单样式改动。主干新增问候快路／昵称已通过正常merge保留。

## 版本与同步

- core 0.7.1、goods 0.6.1、support_ai 0.15.1、web 0.29.1。
- 同步main：`a5e978836e9e3316d24c4204fd7dbe1178c03a4e`。最终源SHA见PR正文；下方源码指纹绑定被验证实现，不包含证据文件本身。
- 0.13.0／0.14.0的实现阶段说明及各模块历史changelog原文保留；本次交付版高于主干support_ai 0.15.0。

## 实际验证

- `python manage.py check --settings=support_ai.test_settings`：0问题。
- `python manage.py test support_ai.tests.RecommendationContractTests support_ai.tests.RecommendationIntegrationTests support_ai.tests.RecommendationGraphTests support_ai.test_semantic_planning support_ai.test_planning support_ai.test_grouped_recommendations support_ai.test_product_details support_ai.test_task_tools support_ai.test_mixed_tea support_ai.test_budget_combinations --settings=support_ai.test_settings --noinput`：99项通过；隔离内存SQLite及本地内存缓存，不连接业务数据库写入。
- 新增7个算法／规则验证方法，包含30组小候选集与独立穷举结果对照；覆盖预算上限、下限、款数、数量、库存准入、茶类覆盖、SPU去重、外币上下界取分和搜索截断。
- `node --test client/tests/checkout.test.js`、`node --test client/tests/product-detail-summary.test.js`、`node --test client/tests/storefront.test.js`：全部通过，详情5项子测试。校验基础金额不变、外币切换、地址保留、支付参数不变和文字安全渲染。
- 初次回归暴露4个后端旧USD／模型调用次数断言及3份前端测试的旧币种／缺依赖夹具。仅同步本次金额契约与规则快路的测试预期，未通过放宽业务过滤来通过测试。
- 18份变更模板编译通过，6个页面以独立交付代码渲染成功并注入同一份CNY配置，13个相关静态资源可定位。未执行浏览器交互业务验收；页面渲染不是浏览器验收。

## 实际商品只读核对

在交付工作区执行规划、受控工具调用与公开商品详情，未调用模型、未创建订单或会话。5个场景通过，详见[只读结果](delivery-live-catalog-check.json)：

| 输入 | 状态 | 人民币上限 | 三套方案的商品合计 |
| --- | --- | --- | --- |
| 总价200，推荐绿茶和白茶 | MATCHED | 200.00 | 198.95／197.70／197.70 |
| 总价200元，推荐绿茶和白茶，每款两件 | MATCHED | 200.00 | 198.98／196.50／196.36 |
| 总价200美元，推荐绿茶和白茶 | MATCHED | 1428.57 | 161.20／149.15／145.00 |
| 总价30元，推荐1款绿茶 | MATCHED | 30.00 | 27.50／23.60／23.60 |
| 总价0.01元，推荐绿茶和白茶 | NO_MATCH | 0.01 | 无 |

逐行检查`price×quantity`之和、预算差额、茶类覆盖、币种与数量；SKU、订单、客服会话和轮次记录数前后相同。美元高预算场景受候选价格和默认2至4款限制，未接近预算；不通过重复商品或超出款数填满预算。最多40候选、有节点／时间边界，不宣称全库最优。

## 本地运行与未覆盖范围

- 已将原本地8000后端重启，PID11868；6个HTTP页面返回200，配置`CNY / 20261022-cny`且加载共用脚本。进程运行在保留其他任务改动的原工作区；交付代码另行完成上述隔离回归与页面渲染。HTTP结果见[runtime-http.json](runtime-http.json)。
- 未执行本轮真实DeepSeek评测、支付调用、数据库迁移、造数或历史金额换算。模型语义准确率、浏览器完整购买流程、实际支付渠道和数据库金额历史对账未据此认定通过。
- Git规范、版本、Migration不可变／编号和Python／JS语法结果绑定最终源提交，见PR正文。提交／推送／MR分别报告；无远端合入、部署或标签发布。
