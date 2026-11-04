# MR35基础CI的可选PDF夹具契约修复

日期：2026-11-04，Asia/Shanghai。针对[MR35](https://github.com/dengbofu-git/shop/pull/35)的Django runtime失败，仅修复ai_storage测试隔离；版本0.8.2。无新增依赖、业务修改、Migration、业务库写入或服务重启。

## 原因与边界

原[Actions任务](https://github.com/dengbofu-git/shop/actions/runs/41756968546/job/126335242260)执行871项，1失败、11跳过。唯一失败为数据库夹具契约子进程手动调用Paddle／Vision数据库测试的setUp，后者为生成样本而import fitz，但基础requirements不安装可选PDF渲染器；约束文件只锁定版本，不负责安装。真实PDF依赖由知识worker独立安装，本地带PDF依赖的环境遮蔽了此缺陷。

契约职责是证明单一PostgreSQL准入、目标身份守卫和无旧驱动时的完整初始化，不承担PDF渲染验收。修复只在契约子进程内用样本生成替身提供open／new_page／文本及线条／save接口，产物明确为不可渲染的sentinel，不把它传给解析器。两个实际夹具的setUpClass和setUp都执行，均断言sentinel生成；仍禁止BaseDatabaseWrapper.connect，保留所有安全准入负例。真实PDF数据库集成代码保持原样，必须使用真实渲染器和专用临时PG。

## 复现与验证

- RED：在子进程显式阻断fitz、pymupdf及旧数据库驱动；`python -m unittest ai_storage.test_pg_fixture_contract`实际5项、1失败，完整复现ModuleNotFoundError，未连接真实数据库。
- GREEN：加入仅限样本生成的替身后，同一命令5项全部通过，2.096秒，无跳过；即使主机安装了渲染器，也不能影响这个回归条件。
- 待取得：同一MR最终提交的Git policy与Django runtime实际结果，写入PR及本机交付收据。不会把本地5项当成871项全套通过。

隔离交付工作区用于保护主目录中5处并行OCR／重排序修改；原文件摘要保持，未混入补丁。现场和原始RED／GREEN日志保存在主目录`.scratch/git-delivery/20261104-ci-pdf-fixture/`。不自动合入PR、发布或回收仍待合入的分支／工作区。
