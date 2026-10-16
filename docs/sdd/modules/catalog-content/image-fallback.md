# 茶类虚拟默认图片

2026-10-16 用户要求：根据当前数据库全部茶种类生成每类虚拟图并入库，商品未上传真实图片时显示虚拟图。归属 CAP-CAT-001／FEAT-004 商品浏览与图片展示，商家上传入口继续归 CAP-CAT-002／FEAT-005。

## 当前数据库与资产

读取当前业务库确认有商品的茶类为红茶、绿茶、乌龙茶、白茶、黄茶、黑茶，共104个SKU；其余7个旧分类没有SKU，不作为本次茶类生成目标。每类使用内置 image_gen 独立生成一张方形茶叶／茶汤产品示意图，采用统一的白瓷、浅石台面和柔光风格。

图片文件保存在 `media/tea_categories/20261016/`，数据库 `goods_catalog.fallback_image` 保存对应媒体路径。生成来源、完整提示词、源文件和SHA256见 [plan.json](../../../../reports/tea-images/2026-10-16/plan.json)。

这6张图表示茶类，不能作为具体SKU的实拍、包装、品牌或资质证明。真实上传字段 `SKU.default_image_url` 和图库 `SKUImage.image` 不写入虚拟图，因此将来上传真实图片无需清理默认图即可优先显示。

## 图片选择规则

1. 当前SKU存在且非空的真实默认图片。
2. 当前SKU图库中的有效图片；失效默认图或失效的首张图库图不遮挡后续有效图片。
3. 当前SKU的旧媒体目录／旧文件。
4. 同SPU其他规格的真实图片，保留原有规格共享规则。
5. 当前商品所属Catalog的虚拟默认图。
6. 无有效茶类图时保留通用占位图；不存在SKU仍返回404。

`goods/images.py` 是统一选择服务。公开商品分类／列表、轮播、详情与同类推荐、收藏／足迹图片API、AI推荐图片API、商家商品列表、采购车和订单／预结算图片均使用此规则。接口字段格式保持原约定：列表／采购车／订单返回media相对路径，图片API返回图像字节。图片API通过 `X-Image-Source: product-upload | catalog-virtual` 标明来源。

## 数据迁移和导入

Migration `goods/0010_catalog_fallback_image.py` 为Catalog新增允许空白的ImageField，不修改任何SKU上传记录。本地业务库已执行并登记6个Catalog路径。

生成资产随项目media目录一起部署。先执行 `python manage.py migrate goods 0010 --database default --noinput`，然后执行：

```powershell
# 默认预览；验证类别、图片格式、SHA256与已有默认图冲突
python manage.py register_tea_images --manifest reports/tea-images/2026-10-16/plan.json
# 原子登记，重复运行同一路径幂等
python manage.py register_tea_images --manifest reports/tea-images/2026-10-16/plan.json --apply
```

已有不同茶类默认图须明确使用 `--replace` 才能覆盖。导入命令不读取用户凭据、不改价格、库存、订单、收藏或真实图片字段。后续新增茶类可追加新资产／清单后复用此命令。

回退优先恢复代码并保留图片及字段；若只撤销本批默认图，用 `reports/tea-images/2026-10-16/before.json` 恢复Catalog原路径。反向迁移会删除新增字段，需人工评估；本次没有执行回退。

## 验收与证据

- 已有真实图时：图片API及列表、采购车、订单显示真实图，Catalog虚拟路径保持不变。
- 无真实图／真实文件缺失时：显示所属茶类图，跨茶类不会混用。
- 上传真实图后：下一次图片读取立即切换，无需额外刷新默认图配置。
- 图片默认字段失效但图库后续图片有效时：选择图库真实图。
- 新导入：先全量验证，事务提交；哈希、图片或分类无效时拒绝，默认预览不写库。

测试为 `goods/test_images.py`，并回归 `goods/test_activity.py`。全量当前库只读核对见仓库文件 `reports/tea-images/2026-10-16/database-audit.json`：104接口正常，102使用虚拟图，2使用真实图，原真实图片路径与文件哈希不变。测试日志与输入哈希见同目录verification.json。

实现版本：goods 0.4.0、carts 0.1.1、orders 0.1.1。未改变商品定价或交易状态语义；图像验证不代表全站业务验收。
