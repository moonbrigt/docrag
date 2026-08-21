# DocRAG 验证记录（Validation）

> 数据核对日期 2026-08-21（WSL 迁移后复核）。本文件记录运行环境的验证实测：后端全量测试、评测确定性、前端构建与真实模型链路。环境唯一为 **WSL（Ubuntu）原生**；Docker 已弃用并移除。

## 1. 验证对象与日期

- 验证基线：`moonbrigt/docrag` 分支 main（基线 `64414d7`）+ 本轮未提交的成熟度改动（ACL/生命周期/版本/no-answer/反馈/trace/评测）。
- 宿主复核执行于 2026-08-12：Python 3.12.3（评测 venv）、node v24.19.0、pytest 9.1.1、fastapi 0.115.13、pypdf 6.15.0、faiss-cpu 1.14.3、numpy 2.5.2。

## 2. 测试文件清单与覆盖点（backend/app/tests/，16 文件 / 109 用例节点）

| 文件 | 用例数 | 覆盖点 |
|------|--------|--------|
| test_documents.py | 5 | 上传→indexed 全流程、列表空态、详情 404、原文文件服务与删除、缺文件 404 |
| test_health.py | 2 | /health 健康状态、/config/backends 后端就绪 |
| test_cache.py | 9 | 查询缓存 TTL/命中/失效（reindex、删除、索引成功时清除）、禁用开关 |
| test_rerank_service.py | 2 | 重排候选池截断（RERANK_CANDIDATES）、全文回查（非 snippet）、小池直通 |
| test_citation.py | 19 | citation 分数透传、引用缓冲校验、引用页过滤与 no_answer 联动 |
| test_maturity_acl.py | 9 | ACL 端点权限、撤权 fail-closed（立即 404）、admin 绕过可见性、CORS 不含 X-Rag-*、检索双路范围限定、文档列表契约字段、显式空范围零结果、本地模式忽略身份头、trusted-proxy 租户隔离 |
| test_maturity_chat.py | 7 | 空库 409、no_evidence 不调用 LLM、not_supported（有证据无引用不泄出 delta）、rerank fail-closed、SSE 全流程契约、trace 访问控制、query 原文不落库 |
| test_maturity_lifecycle.py | 6 | cancel 中途停止并清理、cancel 终态冲突 409、失败→retry 清理 partial、retry 需管理权限、warning 保留 partial、重启恢复（瞬态→failed） |
| test_maturity_versions.py | 5 | 版本 promote 成功才归档、版本替换需管理权限、删除清理 events/trace 一致性、删除竞态、删非 owner 404 |
| test_parser.py | 7（含 6 个参数化） | bbox 归一化 3 例（TOPLEFT/BOTTOMLEFT/边界）、非法几何拒绝 3 例、Docling 懒加载路径 |
| test_public_evaluation.py | 17 | manifest 完整性/缺字段拒绝、下载 hash fail-closed、gold evidence 不匹配 fail、unanswerable 关键词命中 fail、evidence 归一化（大小写/连字符/ligature）、跨文档同页不算命中、hard-negative 指标、检索/引用指标正确性、答案分型判分、bootstrap CI 确定性、切片四维覆盖、报告字节确定性、CLI run、API 未 prepare 409、baseline 不收 gold |
| test_search_eval.py | 4 | 检索命中、空库、chat SSE、evaluation run |
| test_accelerator.py | 5 | 加速设备探测（CUDA 可用/不可用）、mock 降级与配置回写 |
| test_embed_http.py | 2 | OpenAI 兼容 `/v1/embeddings` 后端请求构造与响应解析 |
| test_public_real.py | 4 | 真实模型适配器探测语义（未见权重的 NOT_RUN 契约） |
| test_runtime_config.py | 6 | `runtime_config` 持久化、读时合并、env 覆盖顺序、读取契约 |

## 3. 实测结果

### 3.1 后端全量 pytest：✅ 109 passed（2026-08-21 WSL 复核）

| 项 | 结果 |
|----|------|
| 本次复核（backend venv，`./.venv/bin/python -m pytest -q`） | **109 passed in ~8.7s**，零失败零跳过（在 WSL 实测确认） |
| 覆盖 | 16 文件 / 109 用例节点，含 4 个成熟度测试文件（acl/chat/lifecycle/versions）、公开评测测试、cache / citation / rerank_service、runtime_config / embed_http / accelerator / public_real |
| 修复记录 | 此前发现在 `backend/app/db.py` 上 `_migrate` 先于建表执行会让全新数据库报 `no such table: documents`（当时 23 passed / 38 errors）；修复为 `_migrate` 增加 `sqlite_master` 存在性守卫（表不存在即跳过 ALTER，全新库交 SCHEMA 建表）——新库（pytest 临时库）与既有库双路径回归均通过 |

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
| `ruff check backend`（默认规则集） | ⚠️ 94 条提示（2026-08-21 复测，F401 已清零）：UP045×37、BLE001×18、B008×17、I001×13 及 8 条单发，均为存量风格类非功能问题；未配置 ruff 规则文件，无「零警告」基线可对标 |

## 4. 真实模型链路验收（WSL 实测）

> WSL 迁移后，真实 Docling 解析与检索链路已在 WSL 原生实测（2026-08-20）；真实模型全链路消融评测已于 2026-08-21 补跑（见 §4 末条）。容器与 Docker 已移除。

**执行环境**：WSL（Ubuntu），`RAG_PARSE_MOCK=false`（docling 真实解析）；embedding/rerank/LLM 按设置页运行时配置。

- 上传 `NIST.AI.100-1.pdf`（SHA-256 `7576edb5…` 与 manifest 一致）→ 真实 Docling 解析 **`indexed pages=48 chunks=72`**（对比 mock 路径 5 页）；chunk 为真实 NIST 文本（如 "The Artificial Intelligence Risk Management Framework (AI RMF) is intended to be a living document."），携带 Docling 布局输出的 page_no 与归一化 bbox、HybridChunker 的 section 元数据
- 三篇语料（AI-Agents-in-Depth-zh-CN / NIST.AI.100-1 / NIST.AI.600-1）Docling 重解析并重建索引，共 **583 块**，page_no / bbox / section 溯源字段验证
- 真实语料检索：query "risk management framework" 命中 page 3/26/44 等真实相关页
- chat SSE 全链路（stage/delta/citation/done）：引用页码 3/44/26/7/9 均为 AI RMF 相关章节，citation 含真实 bbox 与 snippet
- 结论：**Docling 真实解析 = VERIFIED**（CPU，48 页 + TableFormer 首次含模型下载约 506MB，全流程约 8 分钟）；bge-m3 嵌入与对话分别走 Ollama 本地模型已验证；bge-reranker-v2-m3 真实 CrossEncoder 已于 2026-08-21 在消融评测中加载验证（见下条）
- 真实模型全链路消融（2026-08-21，`backend/app/evaluation/real_full_runner.py`）：bge-m3（FlagEmbedding 本地权重）+ bge-reranker-v2-m3（CrossEncoder，CPU）+ 真实云端 LLM 四变体消融，18 题全跑通；hybrid_rerank_llm recall@5 0.9375 / MRR 0.9062 / answer EM 0.333 / unanswerable 1.0；词法 vs 神经重排同口径对比：词法零增益（MRR 持平 0.752）、神经 +0.154；检索指标跨 run 一致（确定性成立），报告 `work/real_full_report.json` + `work/real_full_lexical.json`（数字与边界见 BENCHMARK_CARD §12）
- **生产运行时切换全真实配置**（2026-08-21）：runtime_config = docling 解析 + Ollama bge-m3 嵌入 + bge-reranker-v2-m3 重排 + 云端 LLM；端到端 chat 实测（WSL、热缓存、真实 trace）：检索 2.9s + 重排 7.7s（候选 10 × 256 token）+ 生成 12.7s ≈ 23s 总延迟，SSE 全事件流（stage/delta/citation/done）正常，引用含真实 page/bbox；`/config/backends` 三后端 ready=true

## 5. 已知问题清单（2026-08-20 核对）

| # | 问题 | 状态 | 证据 |
|---|------|------|------|
| 1 | `backend/app/db.py` 迁移顺序回归（`_migrate` 先于建表） | ✅ 已修复：`_migrate` 增加 `sqlite_master` 存在性守卫，新库跳过 ALTER；79 passed，新库/既有库双路径验证通过 | §3.1 修复记录 |
| 2 | 新代码 2 处 F401 未用导入 | ✅ 已修复：删除 `test_maturity_acl.py`（json）与 `test_maturity_versions.py`（asyncio）未用导入，107 passed | ruff F401 清零 |

> 本文件验证在 WSL 实测（最近 2026-08-21）；后续任何代码改动需重跑 §3 全量检查并同步更新本文件。
