# PaddleOCR PDF 第一阶段实施与隔离验收

日期：2026-10-28（Asia/Shanghai）。模块 ai_storage 0.7.0。当前开发分支 codex/orders-merchant-isolation，工作区既有大量未提交改动；本次未提交、推送、创建 PR 或改写其他模块。

## 交付行为

- 独立认证 HTTP 服务，固定镜像 sha256:ad0b1f056a76967f9191cd06398e8babb21b49a4673a28c3de5fd31f481884db、PaddleOCR 3.6.0、PaddleX 3.6.1、PaddlePaddle GPU 3.2.1及两份模型权重哈希。
- 版面分析在 CPU，视觉识别在 RTX 4060 8GB；同一持久线程加载/执行 GPU 模型，服务端全局一个推理请求，认证、版本检查、输入/输出上限、无 URL/文件路径、无数据库访问。
- 新增独立 document-backend=paddleocr，默认 legacy；统一页面结构、原始证据、实际像素到 PDF points 映射、模型阅读顺序与表格的列表相对位置、授权域缓存、完整行表格切片及 Unicode 映射。
- Worker 复用现有租约、心跳、取消、恢复和显式发布；阻塞结构/截断问题不能进入 Embedding 或绕过发布。无新增 Migration。

## 实际验证

1. `docker exec tea_saas-knowledge-worker-knowledge-worker-1 python -m unittest ai_storage.test_paddle_document ai_storage.test_vision ai_storage.test_pdf_vision ai_storage.test_pdf_parser_protocol`：58 项通过。覆盖真实 HTTP 夹具、认证、服务身份、并发、GPU 线程上下文、OOM 状态、坐标、阅读顺序、简单 HTML 表格、授权域缓存和旧视觉回归。
2. 在新建、无公开端口的 `dadashop-paddleocr-stage1-postgres` 临时容器中执行 `python manage.py migrate ai_storage --database ai_storage --noinput`：0001～0004 通过。业务身份库端点显式设为 127.0.0.1:1，代码进一步禁止 MySQL 连接。
3. 相同专用测试库执行 `python -m unittest ai_storage.test_paddle_document_database`：4 项通过。覆盖冻结解析版本变更阻止执行、草稿、页面和向量恢复、处理中取消丢弃迟到结果、截断阻止 Embedding 与发布。
4. 两页合成 PDF 的真实模型验收：第一页面原生英文文字，第二页面扫描表格。通过实际 PaddleOCR HTTP 服务和实际本地 Ollama bge-m3，未使用识别或向量夹具。操作者鉴权使用测试夹具，明确未验证业务 MySQL 身份。
5. `docker run --rm --network none ... python manage.py check`：无问题。
6. `docker run --rm --network none ... python manage.py makemigrations ai_storage --check --dry-run`：No changes detected。
7. OCR Compose 和 Worker 可选 overlay 的 `config --quiet` 通过；`git diff --check` 通过。本次未运行全仓库业务测试。

真实验收命令：

```text
docker run --rm --name dadashop-paddleocr-stage1-e2e --network dadashop-document-parser --add-host host.docker.internal:host-gateway --env-file .scratch/paddleocr/test.env --env-file .scratch/paddleocr/client.env -v E:/django/dadashop:/app:ro -v E:/django/dadashop/.scratch/paddle-stage1:/evidence tea_saas-knowledge-worker-knowledge-worker python -u /app/.scratch/paddle-stage1/e2e.py
```

`.scratch/paddleocr/test.env` 仅指向临时测试库，不是业务连接配置。各轮使用独立文件/缓存目录，避免此前成功缓存影响冷缓存请求数断言。

## 真实结果

完整结果见 results.json，原件 sample-input.pdf，扫描页参考图 scan-ground-truth.png，真实模型候选 ocr-candidate.json，片段和映射 chunks.json。模型运行身份见 service-identity.json，源码和样本指纹见 source-fingerprints.json。

- 2 页均完成：第 1 页 native、第 2 页 paddleocr_vl，真实 OCR 请求 1 次。
- 全流程约 17.792 秒，OCR 请求约 9.177 秒，均为本次小样本结果，不能推导长 PDF 吞吐量。
- 4 个片段、4 份真实 1024 维向量，10 处字符切片与坐标检查通过。
- 表格确认 Kenya—120、China—80 与各自行对应；表头 Quantity (kg) 保留。
- 文档保持 draft、任务 awaiting_review，模型输出和无文本序号表格均带审核警告；未发布且普通检索看不到草稿。
- 取消后重试复用完成页面和向量，未新增 OCR 请求。
- 临时 PostgreSQL 容器在证据导出后停止，因 --rm 自动移除；其数据卷由 Docker 清理。测试草稿已随隔离库清理，不在业务知识库中。

## 发现和修复

- 初版 HTTP 线程没有继承 Paddle 动态图上下文，实际请求失败。补充线程初始化，并将加载和执行固定在同一线程。
- 最初表格请求达到客户端 300 秒预算仍未完成，官方 CLI 小预算对照也未及时完成；相关请求失败或被主动终止，没有入库或发布。
- 诊断发现模型实际分配约 2,901,058,304 bytes，但转换后保留池约 7,485,847,808 bytes。将版面移到 CPU，并在模型加载后/页面结束释放未使用池，最终初始化保留约 3,178,523,136 bytes，同一表格随后在约 8～11 秒内完成。这是当前硬件上的实测，不是所有性能问题的通用归因。
- 真实协议中表格 block_order 可以为 null；转换层保留列表相对位置及源序号并要求审核，而不是编造为已确认的正文序号。
- 验收脚本修正了 pgvector 返回 NumPy 标量到公开查询 DTO 的类型转换，以及已命中缓存时的冷缓存断言；没有因此修改业务检索实现。

## 启用与未覆盖

OCR 服务 `dadashop-paddleocr-paddleocr-1` 已启动并 healthy，端口只发布到本机 127.0.0.1:18080；Worker 内通过显式允许的 paddleocr:8080 调用。私有 key 与客户端配置仅在 .scratch，不进入证据。

自动审批拒绝了业务 MySQL 的只读连接检查，理由是用户此前要求 Agent 不直接连接数据库。本次未改用其他路径绕过：业务身份认证未验收、业务 Worker 未切换到新增 overlay、未向业务库导入样本或发布知识。后续需要明确业务侧受控命令验收授权。

本阶段不包括运营上传/修正 UI、复杂合并单元格、跨页表格、逐单元格坐标、完整逐字准确率和真实 RAG 回答验收。300 秒进程恢复看门狗已实现，但未做 GPU 硬挂死故障注入，不能据此声称操作系统级硬截止保证。
