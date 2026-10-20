# 推荐商品下拉改搜索验证

2026-10-20，CAP-MER-005，web0.23.1。用户要求将推荐商品的长下拉框改为搜索；仅修改管理页模板、脚本和局部样式，保留既有草稿／发布及后端商品归属校验。未修改数据库或真实店铺内容，未提交／推送。

## 实际验证

- `node --check client/static/js/merchant-store.js`：通过。
- 使用隔离 `support_ai.test_settings` 的Django Client渲染管理页：200，存在搜索框和结果容器，原下拉框及独立添加按钮已移除；HTML使用新JS/CSS缓存版本。
- `python tools/module_versions.py check`、`git diff --check`：通过。
- 实际8000服务管理页和新版搜索脚本HTTP200，均包含新搜索逻辑且无旧选择器；Django直接读取更新模板及静态文件，无需重启。
- 内置浏览器在8766隔离合成环境操作：原3件推荐保持不变；搜索`150g`匹配12件，只显示6条并提示细化；搜索`春日茶礼 4`定位1件，点击添加后推荐列表增加该件，结果按钮变为“已添加”且禁用。
- 搜索不存在的商品显示明确空结果；Escape清空输入并收起结果。逐项添加至8件后，第9件按钮禁用并显示上限说明；测试结束移除新增项，恢复原3件推荐，页面无未保存修改。没有保存或发布测试改动。

结果截图为合成数据：[推荐商品搜索](recommendation-search.png)。本次没有后端、数据库结构或业务语义变化，未重复运行全量后端测试。

首版后端及迁移验证仍以此前各次证据为准；本次前端内容与首版manifest不同，不以首版文件哈希冒充本次代码快照，当前文件哈希见 [recommendation-search-manifest.json](recommendation-search-manifest.json)。
