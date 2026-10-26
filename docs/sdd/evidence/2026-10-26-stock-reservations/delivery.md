# 库存预留后续增量交付验证

日期：2026-10-26；本次为用户“推送并创建MR”授权下的DELIVERY_ONLY交付，不扩展其他业务。隔离工作区分支codex/orders-stock-reservation-delivery，主工作区及其运行中的8000后端和清理进程保留。

## 范围与主干同步

同步origin/main，基线SHA：184e2f7113fd45a8d3db89a39dd553427290ef97。主干已含初版库存预留、防超卖、防占位及可信支付，本次只交付后续差异：取消／隐藏分离、服务端动作能力、店铺规则审计、同次结算策略快照、新迁移0005、对应页面和SDD。

盘点全部worktree后，保留其他任务的独有改动。与main重叠文件按三方基线合并：保留main既有采购车格式／重复SKU检查、商家激活及归属检查、历史混合单提示、状态筛选、试单／预售发货实现及原有测试。未回退任何其他模块版本。新增迁移0005与本地已启用版本一致，未改历史迁移。

## 最终交付工作区验证

私有运行器为主工作区忽略目录`.scratch/stock-activation-20261026/delivery_checks.py`，使用合成环境配置，不复制业务凭据。MySQL使用专用临时容器、回环13316端口、MySQL8.0.27和tmpfs，未连接业务库试跑。

| 命令与覆盖 | 最终结果 |
| --- | --- |
| `python .scratch/stock-activation-20261026/delivery_checks.py mysql` | 54项全部通过，随机隔离库正常销毁；临时容器随后停止并自动删除 |
| 同runner `regression` | SQLite144项，134通过、10项MySQL专用跳过 |
| 同runner `check` | Django系统检查通过，makemigrations无差异，买家订单／商家订单／商家库存／结算／支付5个模板渲染通过 |
| `node --test client/tests/reservation-checkout.test.js client/tests/merchant-orders.test.js client/tests/merchant-workbench-feed.test.js` | 12项通过 |

MySQL标签：orders.test_reservations、orders.test_reservation_contracts、pays.test_reservation_signatures、supplier.test_order_actions；SQLite额外覆盖engagement.tests、engagement.test_conversations、goods.test_sales_recommendations、supplier.test_workbench、supplier.test_store_pages、goods.test_activity。

首次交付检查因独立worktree缺少必需环境变量、冲突替换误触JS函数声明而失败；运行器补合成配置并纠正该合并错误后，以上最终检查均通过。未因交付修改其他业务缺陷或跳过检查。

完整Diff、精确文件名单、模块版本／changelog及历史迁移不变性由提交检查和推送前`python tools/git_policy.py verify --base origin/main`核对；最终源SHA、同步main SHA及实际门禁结果记录于PR正文，不将历史工作区测试冒充合并后结果。

## 启用与限制

本地业务库备份、限定迁移、原列摘要及服务启动见[启用记录](activation.md)，发生于交付前、使用主工作区源码；交付隔离工作区没有再次迁移或替换运行进程。真实支付／退款未验证，ALIPAY_SELLER_ID缺失时支付链接保持拒绝。回退代码不能撤销已写业务状态或替代数据库恢复；数据库回退和生产发布须另行授权。此PR不自动合入或发布。
