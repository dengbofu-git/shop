# 首页分类分页验证

日期：2026-10-18；web0.11.0。用户要求每页10件、增加分页器，并补充桌面端2行、每行5个。规则见[分类预览规格](../../modules/catalog-content/catalog-preview.md)。未提交、推送或部署。

## 已执行

```powershell
python client/tests/catalog-preview-contract.py docs/sdd/evidence/2026-10-18-catalog-pagination/catalog-contract.json
node client/tests/buyer-catalog-preview.test.js docs/sdd/evidence/2026-10-18-catalog-pagination/catalog-contract.json
```

使用Dadashop环境Python和Node，命令通过。Django脚本只连接自动销毁的SQLite测试库，创建两个有效分类共30件SKU，另含缺货及未上架数据；真实index接口响应经Node执行实际分页脚本，全部分类和每个分类可遍历所有对应SKU且无重复，查看全部链接仍带正确分类ID。首页模板HTTP200，分页容器存在，新脚本加载顺序正确，原四个场景按钮不存在。

额外合成103件、6分类的数据，模拟用户截图中的数量：每页10件、共11页，末页3件，汇总全部分页SKU集合恰为输入集合，无遗漏或重复。覆盖上一页、下一页、页码直达、首末页禁用、分类切换回第一页、语言切换保留第二页、空态隐藏分页、失败重试恢复。页码保留焦点，并返回商品区域。

首页专用CSS在1200px及以上采用5等列、等高网格，10件为2行；窄屏按4／3／2／1列调整。没有改变商品采购页的网格。样式和脚本缓存参数已更新。

## 验证边界

此前内置浏览器访问因URL安全策略被拒绝；本轮未绕过、未新采集截图，也未宣称完成当前5列布局的浏览器视觉、移动端或全链路验收。Node行为与模板／接口契约验证不能替代实际排版观察。

未访问或修改业务数据库，没有真实采购、收藏或支付写入。库存口径仍遵循现有index接口；全部商品指该接口返回的上架且SKU.stock>0商品。其他任务的工作区改动保留。
