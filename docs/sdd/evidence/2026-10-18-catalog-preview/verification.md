# 茶类分类预览验证

日期：2026-10-18，web0.10.0；对应[规则](../../modules/catalog-content/catalog-preview.md)。未提交、推送或部署。原用户截图中四个场景和静态茶类未提供正确筛选；本次改为现有分类接口数据驱动。

## 执行命令与结果

```powershell
python client/tests/catalog-preview-contract.py docs/sdd/evidence/2026-10-18-catalog-preview/catalog-contract.json
node client/tests/buyer-catalog-preview.test.js docs/sdd/evidence/2026-10-18-catalog-preview/catalog-contract.json
node --check client/static/js/buyer-catalog-preview.js
node --check client/static/js/buyer-workbench.js
```

以上由tea_saas Python环境和本地Node执行，全部通过。

契约脚本仅使用support_ai.test_settings的临时SQLite数据库，运行真实Django迁移后创建合成红茶16件、绿茶14件和一个无可售商品的分类，另为各类创建缺货／未上架SKU。真实`GET /v1/goods/index`只返回两个有效分类及30件商品，缺货和未上架数据不出现；自动销毁测试库。响应保存为本目录catalog-contract.json，数据均为合成数据。

真实首页模板HTTP200，四个采购场景按钮不存在，新分类控制器先于原卡片脚本加载。Node实际执行分类控制器并消费Django响应，逐类验证预览SKU均来自所选分类，每类最多12件，查看全部链接的catalog_id正确。另覆盖全部分类轮流预览、分类计数、语言切换保留当前类别、未知茶类原名、空态、网络失败后重试及业务错误响应。

## 范围与限制

本轮尝试通过内置浏览器读取当前买家首页时，工具URL安全策略拒绝授予访问；未采用其他浏览器或绕过方式。未完成当前版本的浏览器视觉、移动端或真实买家全链路验收，没有新截图。模板和Node验证不冒充这些结果。

未访问或修改业务数据库，没有真实采购、收藏或支付写入。分类接口现有库存条件为SKU.stock>0且已上架，本轮未改成库存账本规则。共用采购、收藏、多语言、预览与禁用溯源入口继续沿用现有代码；首页其余区域保留。
