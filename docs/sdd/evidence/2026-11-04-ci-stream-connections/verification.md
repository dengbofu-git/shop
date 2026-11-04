# MR35测试库销毁与线程连接生命周期

日期：2026-11-04，Asia/Shanghai。补充[可选PDF契约修复](../2026-11-04-ci-pdf-fixture/verification.md)后的CI诊断。没有降低检查、强杀数据库会话、保留测试库或绕过Hook。

## 观察与原因

提交146a08a的[首轮CI](https://github.com/dengbofu-git/shop/actions/runs/41760561502)871项断言OK、11跳过，但销毁测试库时ObjectInUse：剩1个session；[后轮](https://github.com/dengbofu-git/shop/actions/runs/41760736182)同SHA全绿，说明存在清理时序问题，不能靠重跑消除。

当前CONN_MAX_AGE=60，close_old_connections只处理过期或异常连接，线程结束时新鲜健康连接仍会保留。代码审计发现流式工作线程finally及商品导入／商家发货／站内咨询测试worker的5处finally使用了该方法；其他线程和测试主线程不能替它释放线程局部连接，GC是否及时执行使销毁结果偶发不同。不凭日志认定远端唯一session属于哪个具体worker。

## 修复与确定性证据

- 流式worker退出finally改为connections.close_all，仅关闭当前工作线程所有连接；入口的过期连接检查、信号、容量释放和原输出语义保持。
- 3个并发测试文件的5处worker finally同样显式关闭；入口检查、原并发安排及业务断言保持，不改变库存／发货／咨询代码。
- 新真实PG回归保留worker wrapper强引用，使GC无法偶然掩盖问题。检查工作结束后wrapper已关闭、后台PID从pg_stat_activity消失，主调用方连接PID仍在；分别覆盖成功、异常和取消。RED自身也在finally释放捕获连接，保证隔离库可正常销毁。
- RED：3项均在新鲜worker连接仍打开的断言失败；GREEN：新增3项加原流式15项共18项全部通过，3.774秒，测试数据库正常销毁。只在本任务独立tmpfs PG／Redis环境运行，不连接业务库，不调用真实模型。
- 完整本次CI命令及最终提交结果由PR检查和本机交付收据记录；不把18项冒充全部系统通过。先前871断言通过也不冒充成功退出。

版本：support_ai0.32.6、goods0.7.7、supplier0.4.8、engagement0.2.6。无Migration、生产部署或本地业务服务重启，主目录并行OCR／重排序修改仍保留。原始日志与资源登记位于主目录`.scratch/ci-connections-20261104/`，Git收据位于`.scratch/git-delivery/20261104-ci-pdf-fixture/`。

完整隔离验证：`run_tests.py full-green orders inventory pays carts goods supplier engagement users support_ai ai_storage logistics`执行874项，867通过／7项专用数据库测试跳过，54.913秒，进程exit0且测试库正常销毁。该镜像装有部分可选PDF依赖，基础CI可能另有4项可选依赖跳过；两者分别记录，不冒充相同覆盖。独立只读审查确认只关闭当前worker连接，测试SQL全为读取，未强杀会话或修改业务库。
