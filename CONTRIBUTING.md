# 参与 tea_saas 开发

仓库：[dengbofu-git/shop](https://github.com/dengbofu-git/shop)。先阅读 [AGENTS.md](AGENTS.md)、[Git 协作规范](docs/Git协作规范.md) 和 [模块版本管理](docs/模块版本管理.md)。

本仓库为个人项目，源码开放获取，仅限非商业使用。参与、复制或分享前请阅读 [LICENSE](LICENSE)；第三方代码与素材仍遵循其原有授权。

每个克隆首次执行：

```powershell
python tools/git_policy.py install
git switch -c codex/core-example
```

依赖：Git、Python 3.9+；交付 JavaScript 修改时需要 Node.js。Git for Windows 使用自带的 sh 执行 Hook；终端需能找到 `python` 和 `node`。

提交示例：`fix(goods): 修复商品库存显示`。只暂存本次授权的文件，代码、对应模块版本和 changelog 一起提交。向 `main` 提交 PR，验证结论按实际命令与结果填写。
