# 本地店铺功能启用记录

日期：2026-10-20（Asia/Shanghai）。类型：local-deployment／verification；CAP-MER-005。用户在首版交付后明确回复“授权”，授权对象为新增店铺表迁移到本地业务库并重启8000服务。该授权不包括Git提交、推送、PR、远端部署或发布真实商家的店铺内容。

## 目标与备份

- 目标：本机 `127.0.0.1:3306/dadashop`，MySQL8.0.27；已核对服务器UUID及迁移计划。
- 执行前使用匹配容器内的 mysqldump 做完整SQL备份，采用single-transaction、quick、no-tablespaces、set-gtid-purged=OFF、routines、events、triggers、hex-blob、utf8mb4；密码只传入子进程环境，不写入命令、文件或日志。
- 本机备份：`.scratch/store-pages/backups/dadashop-before-store-20261020-151121.sql`，876972字节，SHA256 `ffc23de4abc28066c494b0b70baa8d60b15e264edc878ec33a25c81b7c2d0218`。已检查成功退出、建表内容及完整结束标记；未执行恢复演练或自动回退。
- SQL包含真实业务数据，仅保存在Git忽略的本机目录，未复制到共享证据或提交。脱敏操作摘要见 [activation-summary.json](activation-summary.json)。

## 实际执行

1. 比较首版验证manifest中实现文件SHA256，均未变化；迁移图的精确目标只有 `supplier.0002_storepage`，无反向操作。
2. 备份成功后，实际执行 `python manage.py migrate supplier 0002_storepage --database default --noinput`（脚本通过Django call_command调用同一命令）；`Applying supplier.0002_storepage... OK`。没有执行不带目标的全库migrate。
3. 新表 `supplier_store_page` 已创建，记录数为0；未自动给现有商家建店、保存草稿或发布。
4. 对比迁移前后记录数：用户10、SKU104、SPU119、订单112、订单明细111，全部相同。迁移增加的Django内容类型／权限及迁移记录属于框架元数据，此记录数检查不冒充完整数据逐字节一致性检查。
5. 核对旧服务PID30336、解释器及启动参数后停止该服务；以相同解释器和工作目录运行 `python -X utf8 -u manage.py runserver 127.0.0.1:8000 --noreload`。新PID35192，启动检查无问题，监听仍限本机。

## 实际服务只读验收

13项HTTP检查通过，结果见 [local-http-verification.json](local-http-verification.json)：

- 商家工作台包含店铺管理面板入口；`/merchant_store.html?embed=1`、`/store.html?merchant_id=1`与四份新静态资源返回200。新页面允许SAMEORIGIN嵌入。
- 匿名访问管理API返回401。对本地活跃商家使用仅存内存、45秒过期的令牌进行同源GET，配置API返回200和未发布的默认资料；令牌未记录、未写入浏览器、未持久化。GET前后店铺表仍为0行。
- 商品索引、推荐、详情均返回200；索引返回103件可售SKU。当前真实可售目录只关联1位商家，未为演示多商家而改写真实数据；多商家隔离已由首版合成测试与浏览器验证。
- 尚未发布的真实商家公开店铺API返回404，符合筹备中状态。店铺未发布时商品仍在平台展示，卡片不提供失效店铺链接。商家需要自行保存并发布页面后，公开入口才生效。

未保存／发布真实店铺、上传真实素材、执行采购／支付或改变业务状态；未重复执行隔离全量回归。首版浏览器与MySQL验证见 [verification.md](verification.md)。本次实际服务验证为HTTP只读验收，没有代替用户在原浏览器中登录商家并发布的操作。

## 其他状态

原有 `ai_storage.0001_initial`、`ai_storage.0002_embedding_validation` 在default连接的迁移记录中仍被提示未应用，本次未执行。它们不属于本次店铺迁移范围，不能因启动提示自动迁移到业务MySQL。

本地功能启用已完成；没有提交、推送、PR、标签或远端部署。用户可刷新原商家工作台，在“商品管理”下方进入“店铺页面管理”。
