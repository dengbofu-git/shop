# PR #8 Git policy 修复

日期：2026-10-20。模块：core 0.5.1。关联 PR：https://github.com/dengbofu-git/shop/pull/8。

首次失败发生在 GitHub Actions 运行 39391020822 的 setup-python 步骤：Ubuntu 26.04 没有指定 Python 3.9 的运行时产物；其后治理检查均未执行，不能将该次失败解释为业务断言失败。官方 Python 版本清单确认 Python 3.9.25 的 Linux x64 产物包含 Ubuntu 22.04。

将工作流镜像从滚动的 ubuntu-latest 固定到 ubuntu-22.04，保留 Python 3.9、Node 22、所有治理回归及真实源 SHA 检查。没有删除检查、允许失败或跳过 Hook。Node Action 的弃用提示不是本次失败原因，未借此扩大升级范围。

本地复查还发现三份新增启用证据含物理环境的历史名称，会触发既有命名空间检查。仅对共享证据中的库名、工作区／解释器路径与私有备份定位使用别名；原件已保留本机，没有重命名真实数据库、备份或目录，没有修改原始业务数据或历史 Migration，也没有扩大命名空间例外。

实际执行与结果：

- `python -m unittest discover -s tools/tests -p test_git_policy.py -v`：23 项通过。
- `python -m unittest tools.tests.test_project_identity tools.tests.test_module_versions -v`：6 项通过。
- 官方清单只读核对：3.9.25、linux、x64、22.04 匹配。
- `git diff --check`：通过；模块版本及 changelog 同步变更。

这是 CI 配置与共享证据修复，不涉及订单、支付、商品或权限业务改动。远端最终检查结果以该 PR 的新源 SHA 为准，本地测试通过不能替代 GitHub 实际执行结果。
