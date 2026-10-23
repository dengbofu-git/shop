# 实现、迁移与验证

## 2026-10-21 商家收藏增量

新增 `MerchantFavorite` 与 `goods/0011_merchantfavorite.py`，只创建独立表 `goods_merchant_favorite`，包含买家、商家、收藏时间及收藏时公开名称／Logo快照，唯一键为 `(user_id, merchant_id)`。不改现有商品收藏或足迹数据，不回填历史商家收藏。goods 0.6.0、web 0.26.0。

三个商家收藏接口均复用活跃买家鉴权、JWT身份、no-store响应；公开店铺信息由 supplier 规则读取。新收藏在事务中锁定已发布店铺；下线后列表只保留收藏时的公开快照，不暴露私有草稿或账号字段，仍允许幂等移除。名称和简介使用纯文本DOM渲染。

活动页新增商品／商家收藏分类，分别维护页码与空态；商品足迹保持独立页面。分类 URL 支持前进／后退，旧分类请求的迟到响应被丢弃。店铺收藏按钮仅在店铺成功加载后初始化，匿名点击引导登录，失败显示提示，不写商品足迹。

2026-10-22（web0.26.4）：收藏商品和收藏商家卡片不展示记录时间，也不保留时间行的空白；商品价格或商家简介后直接放置查看／取消收藏操作。最近浏览仍展示查看时间。持久化时间字段、按收藏时间倒序的规则和接口响应保持不变。

迁移按仓库要求在独立 MySQL 临时库验证，业务库迁移与重新加载后端在获得授权后进行。没有自动逆迁移；需要回滚时先停用新入口和写入，保留新表以免丢失收藏记录。原有商品收藏及浏览足迹的历史验证记录不作为本次商家收藏的功能验收成绩。

新增 `goods.Favorite` 和 `goods.BrowsingHistory`，分别包含账号、SKU、收藏／最近查看时间，数据库唯一键 `(user_id, sku_id)`，外键级联删除，时间倒序加 ID 作为稳定次序。使用业务 default 数据库。

`activity_views.buyer_only` 复用 JWT 用户读取，在视图外检查账号启用和 customer 类型。业务异常不被认证装饰器捕获成 401；各 API 自行限制 HTTP 方法。列表使用 select_related、12 条数据库分页，足迹页的收藏状态仅批量查询当前页 SKU。

收藏采用显式 PUT／DELETE 而非 toggle，重复请求不会反转状态；唯一约束兜底重复插入。足迹记录、删除和清空使用同一账号行 `select_for_update` 与原子事务，在 MySQL 上串行化；更新同一 SKU 并在事务内裁剪到 100 件。SQLite 不证明 MySQL 行锁行为，相关真实组件结果见 evidence；收藏与取消并发的最终状态取实际提交结果。

详情页只有在现有详情接口成功、`is_launched=true` 时初始化收藏状态及足迹请求。匿名时不写入，点击收藏引导登录。足迹写失败显示提示，不阻断详情。列表以 `textContent` 构建商品文本；操作中锁定按钮，失败显示提示，GET加载失败可重试。

页面复用买家顶部、侧栏和全站主题；独立 CSS 网格采用三／二／一列，监听现有 html.lang 变更。金额明确为当前人民币，不随侧栏币种选项换算。

2026-10-16交互修正：取消正文中重复的收藏／最近浏览切换栏。共用顶部加载 buyer-favorites.js，为异步生成的采购、精选和推荐卡片补充收藏按钮；复用现有SKU收藏GET／PUT／DELETE接口，每个SKU查询一次状态，同页相同SKU同步。推荐链接与按钮分开，捕获收藏点击防止触发整卡采购行为，处理中禁用、失败提示可重试；新增脚本及已修改活动页资源带版本参数以刷新旧缓存。

## 迁移与回退

Migration：`goods/0009_browsinghistory_favorite.py`，依赖 goods 0008 与 users 0007，只创建两张新表和约束。无既有数据回填，无匿名历史合并。

本地运行：`E:\miniconda\envs\tea_saas\python.exe manage.py migrate goods 0009 --database default --noinput`。本次已成功；其他环境需随代码执行迁移。联合版本 goods 0.3.0、web 0.5.0、core 0.1.4。

回退先回滚页面与 API 代码，可保留新增表以便恢复。若需回退到 goods 0008，先备份新增两表并确认可丢弃收藏与足迹，再人工反向迁移；本次没有执行反向迁移。

## 证据范围

自动场景见 `acceptance.yaml`、`goods/test_activity.py`，SQLite 使用 support_ai.test_settings，MySQL 使用 goods.test_mysql_settings 创建唯一临时测试库，结束自动删除，不在业务库中造测试用户。

浏览器预览脚本 `docs/sdd/evidence/2026-10-16-buyer-activity/preview.py` 使用临时SQLite和合成账户／商品，127.0.0.1:8001；bootstrap仅属于验证脚本，不挂载业务路由。截图、命令、输入哈希和限制见 evidence 的 manifest.json、verification.md。阶段保持 IMPLEMENTING 等待人工审阅。
