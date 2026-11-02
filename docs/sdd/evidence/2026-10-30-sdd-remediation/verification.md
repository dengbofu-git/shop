# SDD交接后的首批修复

基线为`0d53d1423cbeb349730ff9462e5798fb5f58cb59`。在持久主目录的`codex/core-sdd-remediation`分支实施，保留交接已有16份SDD改动和提纯证据；原MR30不包含本轮增量。范围为用户确认的履约读取矩阵和既有“无来源不展示为真实数据”规则。

## 改动与边界

- [履约读取矩阵](../../modules/trade/fulfillment-read-scope.md)：本人买家、本店完整订单、平台显式权限；停用、撤权、跨账号、跨商家及混合历史单拒绝路径。
- 旧数据中心移除按订单哈希生成的地区、推算周转、虚构漏斗和伙伴/ROI/仓库健康度/满意度数值，返回null并保留TODO；前端用占位符和暂无可靠数据说明，不将缺失值转换为0。真实销售、分类和订单统计保持；商家归属对齐购买时快照。
- 四个模块版本：logistics0.1.2、inventory0.2.2、supplier0.4.3、web0.35.1，附各模块changelog。新增迁移：无。
- 现行SDD中的两处旧工程名称改为当前工程名或物理路径通用说明；历史提纯evidence未改写。

## 验证

- `manage.py test logistics.test_scope inventory supplier.test_analytics supplier.test_insights supplier.test_workbench --settings=support_ai.test_settings --noinput`：隔离SQLite，39项全部通过，无跳过。首次一项原测试把地区假数据计入销售聚合，随新契约改为验证真实聚合及unknown来源，再完整重测通过。
- `node client/tests/operations-dashboard.test.js`：通过；实际执行缺失值占位、地区/漏斗不创建图表，以及原图表重试、周期切换、竞态与销毁检查。`node --check client/static/js/operations-dashboard.js`通过。
- `manage.py test logistics.test_scope supplier.test_analytics --settings=scope_mysql_settings --noinput`：临时设置固定到无业务挂载、随机回环端口的独立MySQL8.0.27，17项全部通过，无跳过；测试库销毁，临时容器已停止。未连接业务库试跑。
- `python -m unittest tools.tests.test_project_identity -v`：4项全部通过；首次发现继承SDD中的两处旧工程名称，已仅修正文档名称和物理路径通用说明后重测通过。

未提交、推送、创建新PR、重启或迁移业务库；未读取真实买家物流数据、调用承运商/模型。R01/R02、R05/R06/R08/R09及其余业务分支继续按提纯报告逐项处理，本证据不将它们提升为已完成。
