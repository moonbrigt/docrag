# DocRAG 验证记录（Validation）

> 本次文档更新，数据核对日期 2026-08-12。本文件分两部分：(a) 宿主验证（本次复核实测）；(b) 容器验收（2026-08-12 集成阶段实测数据，见 §4）。

## 1. 验证对象与日期

- 验证基线：`moonbrigt/docrag` 分支 main（基线 `64414d7`）+ 本轮未提交的成熟度改动（ACL/生命周期/版本/no-answer/反馈/trace/评测）。
- 宿主复核执行于 2026-08-12：Python 3.12.3（评测 venv）、node v24.19.0、pytest 9.1.1、fastapi 0.115.13、pypdf 6.15.0、faiss-cpu 1.14.3、numpy 2.5.2。

## 2. 测试文件清单与覆盖点（backend/app/tests/，9 文件 / 61 用例节点）

| 文件 | 用例数 | 覆盖点 |
|------|--------|--------|
| test_documents.py | 5 | 上传→indexed 全流程、列表空态、详情 404、原文文件服务与删除、缺文件 404 |
| test_health.py | 2 | /health 健康状态、/config/backends 后端就绪 |
| test_maturity_acl.py | 9 | ACL 端点权限、撤权 fail-closed（立即 404）、admin 绕过可见性、CORS 不含 X-Rag-*、检索双路范围限定、文档列表契约字段、显式空范围零结果、本地模式忽略身份头、trusted-proxy 租户隔离 |
| test_maturity_chat.py | 7 | 空库 409、no_evidence 不调用 LLM、not_supported（有证据无引用不泄出 delta）、rerank fail-closed、SSE 全流程契约、trace 访问控制、query 原文不落库 |
| test_maturity_lifecycle.py | 6 | cancel 中途停止并清理、cancel 终态冲突 409、失败→retry 清理 partial、retry 需管理权限、warning 保留 partial、重启恢复（瞬态→failed） |
| test_maturity_versions.py | 5 | 版本 promote 成功才归档、版本替换需管理权限、删除清理 events/trace 一致性、删除竞态、删非 owner 404 |
| test_parser.py | 7（含 6 个参数化） | bbox 归一化 3 例（TOPLEFT/BOTTOMLEFT/边界）、非法几何拒绝 3 例、Docling 懒加载路径 |
| test_public_evaluation.py | 16 | manifest 完整性/缺字段拒绝、下载 hash fail-closed、gold evidence 不匹配 fail、unanswerable 关键词命中 fail、evidence 归一化（大小写/连字符/ligature）、跨文档同页不算命中、hard-negative 指标、检索/引用指标正确性、答案分型判分、bootstrap CI 确定性、切片四维覆盖、报告字节确定性、CLI run、API 未 prepare 409、baseline 不收 gold |
| test_search_eval.py | 4 | 检索命中、空库、chat SSE、evaluation run |

## 3. 宿主验证实测结果（2026-08-12 复核）

### 3.1 后端全量 pytest：✅ 61 passed（迁移回归已修复）

| 项 | 结果 |
|----|------|
| 本次复核（评测 venv，`python -m pytest -q`） | **61 passed in ~3.4s**，零失败零跳过（2026-08-12 多次复跑：3.38s / 3.42s / 3.50s） |
| 覆盖 | 9 文件 / 61 用例节点，含 4 个成熟度测试文件（acl/chat/lifecycle/versions）与公开评测测试（test_public_evaluation 16 项） |
| 修复记录 | 复核期间发现并定位 `backend/app/db.py` 迁移顺序回归（`_migrate` 先于建表执行，全新数据库报 `no such table: documents`，当时实测 23 passed / 38 errors）；已由集成阶段修复：`_migrate` 增加 `sqlite_master` 存在性守卫（表不存在即跳过 ALTER，全新库交 SCHEMA 建表）——**新旧库双路径回归验证通过**（新库：pytest 临时库；旧库：既有卷迁移） |

### 3.2 评测专项（独立于 3.1 的 db 初始化，可复现）

| 项 | 结果 |
|----|------|
| `public_runner run` 复跑（独立工作目录） | 成功，`run OK: 16/18 eligible`；指标/CI/切片/per_query 与 `work/eval_reports/public_nist_report.json` **字节一致**（仅 `created_at`、`corpus.source_cache` 路径字段因工作目录而异） |
| 报告 `determinism.verified` | true（运行时自检 + 独立复跑双重确认） |
| 数字核对 | 与 BENCHMARK_CARD §3 表逐项一致（如 recall@1 0.625、mrr 0.746875、eligible 16/18、unanswerable_correct 0.0、provenance 全 NOT_RUN） |

### 3.3 前端与静态检查

| 项 | 结果 |
|----|------|
| `npm run build`（tsc --noEmit && vite build） | ✅ 通过（vite 8.2.1，1965 modules，built in 450ms） |
| `npm run lint`（eslint .） | ✅ 零告警 |
| `ruff check backend`（默认规则集） | ⚠️ 73 条提示：含 **2 条 F401 未用导入**（`tests/test_maturity_acl.py:9` `json`、`tests/test_maturity_versions.py:9` `asyncio`，均可 `--fix`），其余为基线存量风格类（UP045×25、B008×17、BLE001×13、I001×9 等，非本轮引入的功能问题）；默认规则集不含 E501，另行启用行宽检查时 96 条；未配置 ruff 规则文件，无「零警告」基线可对标 |

## 4. 容器验收（2026-08-12 集成阶段完成，下表为实测数据）

> 验收在隔离栈 `docrag-acceptance`（`docker-compose.acceptance.yml`：project 名 docrag-acceptance、入口 127.0.0.1:3302、卷 `docrag-acceptance_draccept_data` / `docrag-acceptance_draccept_models` / `./work:/work`、默认 MOCK + `RAG_TRUSTED_PROXY=true`）上进行。

| 容器 | 镜像 ID / 摘要 | 状态 | health | 重启次数 | 端口映射 | 卷挂载 | 日志要点 |
|------|---------------|------|--------|----------|----------|--------|----------|
| docrag-acceptance-backend-1 | `docrag-acceptance-backend:latest`<br>ID `daf555f3cf3d`，digest `sha256:daf555f3cf3d88fb71039d4c04eb9061171208b9f0c4d52922015150d4969898` | Up | **healthy**（start_period 20s、interval 10s、retries 12，探测 `/api/v1/health`） | 0 | 8000/tcp（仅经前端 nginx 反代，无宿主直出） | `draccept_data:/data`、`draccept_models:/models`、`./work:/work`（评测工作目录持久化） | JSON 单行 `request.handled` 健康心跳；`startup.done` 一次 |
| docrag-acceptance-frontend-1 | `docrag-acceptance-frontend:latest`<br>ID `cf62d21fddbc`，digest `sha256:cf62d21fddbcc3170b30dc17f44db695a14ed0d060969e584bf24cc1c1cd53fc` | Up | —（无 healthcheck） | 0 | `127.0.0.1:3302 → 80` | —（镜像内置 nginx 配置） | nginx 访问日志 |

健康检查实测：`GET http://127.0.0.1:3302/api/v1/health` → `{"status":"ok","db":true,"models":{"embed":{"backend":"mock","status":"ready"},"rerank":{"backend":"mock","status":"ready"},"llm":{"backend":"mock","status":"ready"}}}`。

**容器内执行清单（2026-08-12 集成阶段完成）**：

- [x] `docker compose -f docker-compose.acceptance.yml build`（镜像 ID/摘要见上表；compose config 校验通过）
- [x] `up -d --wait`：backend `Up (healthy)`、frontend `Up`，重启次数 0，日志无异常
- [x] 容器内 `pytest -q`（backend）：与宿主一致 **61 passed**（MOCK 环境全离线）
- [x] 容器内 `public_runner prepare && run`：报告与宿主 `work/eval_reports/public_nist_report.json` 数字一致（确定性验证，`determinism.verified=true`；`./work:/work` 绑定挂载使容器内 `prepare/run` 直接读写宿主 `work/`）
- [x] 纵向验收：上传→解析/分块/索引→检索/重排→回答→精确页码引用→无答案→JSON 导出（chat SSE 含 stage/delta/citation/no_answer/done 事件）
- [x] cancel/retry/失败终态、容器重启后索引/对话/引用状态恢复（重启恢复：瞬态→failed，reason=service_restart_interrupted）
- [x] 上传与产物权限（ACL fail-closed，trusted-proxy 身份：nginx 注入 default/demo）、跨服务错误传播、日志脱敏（query 原文不落库）
- [x] 卷持久化：`down`（不带 `-v`）后重启数据仍在（`draccept_data` 内 SQLite/PDF、`./work` 内缓存与报告）
- [x] **真实 Docling 解析验收（2026-08-12 补充，acceptance 镜像档）**：`docker build --target acceptance -t docrag-acceptance-backend:acceptance ./backend`（docling==2.117.0 + torch，镜像 9.24GB，含 libxcb/libGL 系统库），容器内 `RAG_PARSE_MOCK=false` + mock embedding/rerank/LLM：
  - 上传 `NIST.AI.100-1.pdf`（SHA-256 `7576edb5…` 与 manifest 一致）→ 真实 Docling 解析 **`indexed pages=48 chunks=72`**（对比 mock 路径 5 页）；chunk 为真实 NIST 文本（如 "The Artificial Intelligence Risk Management Framework (AI RMF) is intended to be a living document."），携带 Docling 布局输出的 page_no 与归一化 bbox、HybridChunker 的 section 元数据
  - 真实语料检索：query "risk management framework" 命中 page 3/26/44 等真实相关页
  - chat SSE 全链路（stage/delta/citation/done）：引用页码 3/44/26/7/9 均为 AI RMF 相关章节，citation 含真实 bbox 与 snippet
  - 结论：**Docling 真实解析 = VERIFIED**（CPU，48 页 + TableFormer 首次含模型下载约 506MB，全流程约 8 分钟）；bge-m3 / bge-reranker / LLM 仍 `NOT_RUN`（无权重/密钥授权，见 §4 下表与 BENCHMARK_CARD §10）

## 5. 已知问题清单（2026-08-12 核对）

| # | 问题 | 状态 | 证据 |
|---|------|------|------|
| 1 | `backend/app/db.py` 迁移顺序回归（`_migrate` 先于建表） | ✅ 已修复：`_migrate` 增加 `sqlite_master` 存在性守卫，新库跳过 ALTER；61 passed + 容器旧卷迁移双路径验证通过 | §3.1 修复记录 |
| 2 | `scripts/docker/manage.sh eval` 的 `--profile` 参数与 `public_runner` 不符 | ✅ 已修复：改为 `run --rm -v "$ROOT/work:/work" backend sh -c "python -m app.evaluation.public_runner $*"`（子命令直传：`manage.sh eval prepare|run|verify`，读写宿主 `work/`） | `scripts/docker/manage.sh:50` |
| 3 | 新代码 2 处 F401 未用导入 | ⬜ 未修（ruff 提示，可安全删除） | `test_maturity_acl.py:9`（json）、`test_maturity_versions.py:9`（asyncio） |

> 本文件记录的验证均在 2026-08-12 完成；后续任何代码改动需重跑 §3 全量检查并同步更新本文件。
