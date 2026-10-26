# 库存预留与防占用复核

日期：2026-10-26；[当前规格](../../modules/trade/stock-reservations.md)。源码工作区为codex/orders-merchant-isolation，保留其他任务已有改动。以下为实现及隔离验证阶段记录，该阶段未提交、推送、操作业务库或重启8000服务；随后获单独授权的本地迁移及服务启动见[启用记录](activation.md)。10月22日结果及业务数据摘要仅为历史证据，不代表本轮业务库状态。

## 实现与范围

保留订单原子预留、按商家拆单、幂等、固定截止、可信付款、超时释放及频控预算。按更新后的R04/R07补齐：隐藏不隐式取消；服务端返回买家和商家动作能力；兼容商家删除只取消待付款普通单并留档；历史试单／预售校验子状态及定金尾款，重复发货只出库一次；新增ReservationPolicyChange及orders.0005，要求变更依据并同事务记审计。结算内固定店铺策略快照，规则修改不延长旧预留。

## 实际验证

使用项目Python环境、Django3.2.12及现有Node；私有运行器和日志仅在忽略目录.scratch/stock-reservation-20261022，不含业务库测试。对应公共测试标签为orders.test_reservations、orders.test_reservation_contracts、pays.test_reservation_signatures，以及下述回归模块。

| 实际命令 | 结果 |
| --- | --- |
| `python .scratch/stock-reservation-20261022/run_checks.py mysql-isolated` | MySQL8.0.27，33项全部通过；新增迁移在随机隔离库执行，测试库正常销毁 |
| 同runner `regression` | SQLite123项，114通过、9项MySQL专用跳过；含咨询／评价、销售推荐、商家工作台、店铺与收藏回归 |
| 同runner `check` | Django检查通过，makemigrations无差异，4个受影响模板实际渲染通过 |
| `node --test client/tests/reservation-checkout.test.js client/tests/merchant-orders.test.js client/tests/merchant-workbench-feed.test.js` | 12项通过 |
| `python tools/module_versions.py check`、本轮文件`git diff --check`、Python AST及受影响JS语法检查 | 16个模块归属完整，未发现检查错误；旧inventory.0002/orders.0004哈希与10月22日一致 |

MySQL包含真实多连接竞争库存99／50、付款与取消竞争、重复发货、同幂等编号并发、账号跨SKU累计限额及历史多SKU锁顺序。新契约验证覆盖待付隐藏拒绝、取消后隐藏无库存副作用、试单／预售独立状态、缺失子记录／混合归属拒绝、历史发货不侵占他单预留、取消留档、规则审计与只影响新订单。支付验签使用本地生成的测试密钥及真实SDK，不连接支付渠道。

本轮开始时业务MySQL容器master未运行，原连接测试因端口拒绝连接未能创建测试库，随后改为专用临时容器tea-saas-stock-check-20261026、127.0.0.1:13316、同版本缓存镜像及tmpfs数据目录。初次健康检测早于SQL就绪，改用实际SQL确认后测试通过。临时容器已停止并自动删除，master仍为exited；未启动或修改业务数据库。

## 启用边界

8874页面验证仅使用独立SQLite、测试账号、专用签名密钥及替身Redis。商家表单无依据时阻止提交，填写后显示保存成功，独立库新增1条策略审计。买家结算明确提交10件，订单页显示取消释放且不显示隐藏；确认取消后显示关闭及隐藏入口；再隐藏只从列表移除，订单留存且库存保持实物100／预留0／可售100，持有记录为released。截图留在本机忽略目录。本轮未实际向支付渠道付款。

业务库当前迁移状态未重新核验；待授权后先备份并审阅实际限定计划，目标orders.0005_reservationpolicychange及所需依赖，禁止无条件迁移所有App。重启正式后端时须同时启动watch_stock_reservations或配置周期清理任务。

不自动转换、关闭或预留历史待付订单；历史归属和库存需先核验。迟到到账仅记录退款待处理异常，不自动退款。企业认证、设备识别、验证码、真实支付／退款、生产负载及生产部署未实施或验证；当前限额为试运行默认值，不保证完全阻断多账号攻击。
