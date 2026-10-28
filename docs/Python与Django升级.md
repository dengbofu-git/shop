# Python 与 Django 运行基线

第一阶段采用 Python 3.13、Django 5.2 LTS。当前验证组合为 Python 3.13.18 / Django 5.2.18；Python 小版本由 `.python-version` 指定，Python 安全补丁可在 3.13 系列内另行验证更新。

## 安装与启动

在项目根目录，用独立 Python 3.13 环境安装，保留旧环境作为回退选择：

```powershell
uv venv .venv --python 3.13
uv pip install --python .venv/Scripts/python.exe -r requirements.txt
& .venv/Scripts/python.exe manage.py check
& tools/runtime/preview.ps1 -Python .venv/Scripts/python.exe
# 仅重启由此启动器登记且身份一致的进程
& tools/runtime/preview.ps1 -Python .venv/Scripts/python.exe -Restart
```

普通 pip 同样支持 `python -m pip install -r requirements.txt`。`requirements.txt` 引用 `constraints-py313.txt`，约束中包含 Worker 可选依赖，但不会因此把这些可选依赖安装到 Web 环境。更新依赖时要同时更新约束并复测，不能仅修改 requirements 中的版本。

本机本轮解释器位于 `.scratch/runtime-py313/Scripts/python.exe`；启动器可通过 `-Python` 指向它。启动只运行开发服务器，不执行数据库迁移。启动器在端口被其他进程占用时停止，不能据此结束不明进程。

## 兼容调整与边界

- MySQL 使用原生 mysqlclient 2.3.0，移除 PyMySQL 的 MySQLdb 替换；连接地址、库名、字符集和业务金额不改动，不伪造驱动版本。
- django-cors-headers、django-redis、PyJWT、requests、Pillow 与 greenlet 使用锁定的兼容版本。OTel 仍为 1.41.1；AI 主框架及 OpenAI、Pydantic、LangSmith 等既有配套基线固定在约束文件。
- 删除已经移除的 `USE_L10N` 设置；订单日期范围改用 `ZoneInfo('Asia/Shanghai')`，仍按北京时间起日包含、终日次日零点排除计算。
- 隔离数据库设置先复制字典再覆盖连接，避免测试发现阶段污染其他测试／请求的数据库配置。NumPy 原生扩展在模拟模块清理前导入，避免 Python 3.13 重复导入错误。
- 保留全部历史 Migration。Django 5.2 仍兼容历史 `CheckConstraint(check=...)`；迁移到未来不支持该参数的版本前需另行评估，不能改写历史文件。
- 不更新 MySQL、PostgreSQL、Redis 引擎；不更新嵌入、重排序、OCR、AI SDK 主版本或前端框架，不重建向量索引，不更改页面结构及接口业务规则。
- MCP SDK 仍在独立 Python 3.12 环境，Django 桥接子进程使用应用的 Python 3.13 解释器。

## Worker 与验证

知识库 Worker 使用 Python 3.13 Bookworm 基础镜像，增加 mysqlclient 编译所需的系统依赖，共用同一约束文件。Worker 配置变更不等于容器已重新构建并启用。原 OCR、重排序和 Ollama 容器保持独立版本。

```powershell
docker compose -f compose.knowledge-worker.yml build knowledge-worker
```

镜像源不可用时，可用 Dockerfile 的 `PYTHON_IMAGE` 构建参数选择已核对的同源镜像；不要修改全局 Docker 配置或数据库镜像来绕过问题。

配置检查与迁移差异检查不能替代业务回归。最低验证包括登录和权限、商品与采购车、库存预留与幂等下单、可信支付回调、订单查询、客服多轮、总价搭配、真实本地 MCP 传输、知识检索，以及页面和静态资源。真实模型调用另行核对当次授权。

本轮验证记录见 [升级证据](sdd/evidence/2026-10-28-python-django-upgrade/verification.md)。MySQL 与 PostgreSQL 使用隔离库跑迁移链及回归；业务库只读检查。商品导入等其他任务留下的待执行迁移不由此次框架升级自动启用。

## 回退

保留旧解释器和升级前文件基线。出现回归时，先只停止已核实身份的升级预览进程，再使用升级前源码与原解释器启动。不得使用旧解释器直接运行已升级的依赖／设置，也不以反向迁移业务库实现运行时回退。本次未对业务库迁移或改写数据。

版本支持与升级依据：[Django 下载与支持表](https://www.djangoproject.com/download/)、[升级指南](https://docs.djangoproject.com/en/5.2/howto/upgrade-version/)、[数据库驱动说明](https://docs.djangoproject.com/en/5.2/ref/databases/)。
