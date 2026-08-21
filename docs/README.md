# DocRAG 开发文档索引

> 本文档是 DocRAG 项目的**唯一事实来源（Single Source of Truth）索引**。实现细节一律以「源码 + 本文档」为准；任何其他文档与源码/本文档冲突时，按 §3 声明的优先级裁决。
> 由 2026-08-10 文档梳理建立，目标：**0 歧义**（规格契约可执行、文档与代码一一对应）。

---

## 1. 文档分层图

| 层 | 文档 | 内容 | 何时更新 |
|----|------|------|----------|
| 产品 | 需求 F1–F10 已固化于 SPEC §4/§5（原顶层 `PRD-文档RAG应用.md` 已移除） | 需求变更时 |
| 调研 | （技术调研文档已移出项目目录，存档于 `Documents/项目参考存档/`；选型结论已固化在本文档 §2 速查表与 SPEC §4） | 历史过程 |
| 规格 | `docs/SPEC.md` | **Spec as Contract**：MVP 范围、API/DB/页面/Token/验收标准，开发唯一依据 | 契约变更时在 §13 追加记录 |
| 架构 | `docs/architecture.md` | 分层图、数据流、混合检索、部署拓扑、关键决策 | 架构演进时 |
| 设计 | `frontend/src/design/`（DESIGN.md / design-tokens.json / component-states.md / wireframes.md）+ `frontend/src/styles/tokens.css` | 设计系统权威版（早期 web 稿已移除） | 设计变更时；**token 以 design-tokens.json 为源** |
| 实现 | 本文档 `docs/README.md` + 源码 | 速查表、裁决记录、维护规则 | **每次改代码必同步** |
| 部署 | `docs/DEPLOYMENT.md` | WSL 原生部署、真实模型切换、env 一览、故障排查 | 部署/配置变更时 |
| 测试 | `backend/app/tests/`（smoke + 成熟度 + 评测 + cache/citation，107 项） | 接口冒烟、ACL/生命周期/版本/chat 契约、检索质量与缓存/引用断言 | 每次改代码必跑 `pytest -q` |
| 工程说明 | `docs/ENGINEERING.md` | 关键决策、技术权衡、验证状态与已知边界 | 架构或验证状态变化时 |
| 成熟度审计 | `docs/MATURITY_MATRIX.md` | 10 维度成熟度矩阵（✅/🆕/⬜/❓）+ 市场基线对照 | 功能/权限/状态机变化时 |
| 数据卡 | `docs/DATA_CARD.md` | 评测数据集来源、许可、页码映射、gold 结构与声明 | 数据集变更时 |
| 基准卡 | `docs/BENCHMARK_CARD.md` | 指标口径、基线结果、CI/切片、确定性、provenance | 每次评测报告更新时 |
| 评测协议 | `docs/EVALUATION_PROTOCOL.md` | 数据集生命周期、gold 隔离硬规则、判分协议、本地执行 | 评测流程变化时 |
| 复现指南 | `docs/REPRODUCE.md` | 本地复现路径、预期输出（expected vs observed） | 命令或产物变化时 |
| 验证记录 | `docs/VALIDATION.md` | 本地验证实测数据、已知问题 | 每次验证后 |

## 2. 关键事实速查（与源码核对过的当前值，2026-08-21 复核）

| 项 | 当前值 |
|----|--------|
| 前端 | React 19 + Vite 8 + TypeScript 5.6 + Tailwind CSS 4 + Radix UI + lucide-react + pdfjs-dist 6 + TanStack Query 5 + Zustand 5 + react-router-dom 6 |
| 后端 | FastAPI 0.115.13 + Pydantic 2.11 + Uvicorn/Gunicorn + pydantic-settings |
| 解析 | docling / pdf / mock（`RAG_PARSE_BACKEND` 默认 docling；HybridChunker 透传 `page_no` + `bbox`；pdf=pypdf 轻量按页抽取） |
| 嵌入 | bge-m3 / http / mock（默认 bge-m3；http=OpenAI 兼容 `/v1/embeddings`；dense 1024 维 + sparse） |
| 向量 | SQLite(BLOB) + FAISS 1.14.3（IndexFlatIP，归一化 = cosine） |
| 关键词 | SQLite FTS5（trigram；1–2 字中文 LIKE 兜底） |
| 重排 | bge-reranker-v2-m3 / mock（本地 CrossEncoder / 词重叠） |
| 融合 | RRF(k=60) → top-20 → 截断 `RAG_RERANK_CANDIDATES=10` → 重排（全文、`RAG_RERANK_MAX_TOKENS=256`）→ top-5 |
| LLM | openai SDK + base_url：mock / ollama / openai（mock 确定性流式、默认；ollama/openai 为真实后端） |
| 文档版本 | source_id + version（首版=1，替换原子 +1）+ is_active/archived_at；索引成功才 promote 归档旧版；`POST/GET /documents/{id}/versions` |
| 文档生命周期 | cancel（仅瞬态，冲突 409）/ retry（failed/warning/cancelled 原子认领）；启动恢复瞬态 → failed；见 `docs/MATURITY_MATRIX.md` |
| SSE 事件（/chat） | `stage`（retrieving/reranking/generating）/ `delta` / `citation`（含 sourceId/version/title/createdAt + rrfScore/faissScore/ftsScore）/ `no_answer`（no_evidence/not_supported）/ `done`（selected_document_ids + trace_id）/ `error` |
| API 前缀 | `/api/v1`（22 个端点，见 §4） |
| DB 表 | documents（含 ACL/生命周期列）/ chunks / chunk_fts(FTS5 trigram) / evaluations / document_events（状态流转审计）/ trace（query 原文不落库）/ feedback / runtime_config（运行时模型配置覆盖；单文件 `app.db`，WAL） |
| 文档状态机 | queued → parsing → chunking → embedding → indexed / warning（部分成功保留分块）/ failed（清理 partial）/ cancelled（终态）；重启时瞬态 → failed（service_restart_interrupted）；cancel/retry 原子认领 |
| 身份与 ACL | `RAG_TRUSTED_PROXY=true` 时从 X-Rag-Tenant/User/Group 头解析身份（由可信反向代理注入，浏览器不可伪造）；否则本地默认（default 租户）；可见性 fail-closed（无权限 404/空结果），管理操作限属主/管理员 |
| 无答案 | SSE `no_answer` 事件（`no_evidence`=检索无有效信号不调 LLM；`not_supported`=有证据但生成无有效引用，delta 绝不提前泄出）；空知识库 /chat 409 |
| 反馈与追踪 | `POST /feedback`（rating + issue_type + 评论）、`GET /trace/{id}`（ACL 过滤；query 原文与可反查哈希不落库） |
| 评测集 | 默认 `public_nist`：2 份 NIST PDF / 103 chunk / **18 题**（16 answerable + 2 unanswerable，含 2 条中文跨语言题，gold 为自建页码证据，非 NIST 官方 benchmark）；`synthetic_smoke`：旧 2 篇内嵌文档 / 12 页 / **22 条**中英问答 |
| 评测指标 | 检索 Recall/Precision/Hit@K + hard_negative_recall@K、MRR、nDCG@K、citation page precision/recall + hard_negative_citation_rate、answer EM/F1（exact/set/rubric/numeric 容差/unanswerable 弃答判分）、bootstrap(seed=0) + Wilson CI、language/answer_type/tag/document 切片、provenance（真实模型适配器 VERIFIED/NOT_RUN）、报告确定性自检（见 `docs/BENCHMARK_CARD.md`）；真实模型四变体消融收录于 BENCHMARK_CARD §12（`real_full_runner.py`，recall@5 0.9375 / MRR 0.9062 / answer EM 0.333；词法重排零增益、神经重排 MRR +0.154） |
| 指标端点 | 6 计数器（document_uploads_total / documents_indexed_total / documents_failed_total / queries_total / citations_returned_total / errors_total）+ 4 直方图（http_request_latency_ms / pipeline_latency_ms / retrieve_latency_ms / llm_latency_ms，含 p50/p95/max） |
| 设计 Token | accent `#3E63DD` / citation `#F5B544`；dark 默认 + light 双主题（`data-theme`）；禁 emoji / 紫粉渐变 / 硬编码色 |
| 缓存 | `RAG_CACHE_TTL`（默认 300 秒，hybrid_retrieve 结果缓存 TTL；0=禁用）；reindex / 文档删除 / 索引成功时自动失效 |
| MOCK 开关 | `RAG_LLM_MOCK` / `RAG_EMBED_MOCK` / `RAG_RERANK_MOCK` / `RAG_PARSE_MOCK`（默认全 true，离线可跑；false 时按 `*_BACKEND` 走真实模型）；`RAG_TRUSTED_PROXY`（默认 false，true 时信任反向代理注入的 X-Rag-Tenant/User/Group 身份头） |
| 部署 | WSL（Ubuntu）原生：后端 `backend/.venv/bin/uvicorn app.main:app`，前端 `npm run dev/build`；`backend/start_mock.sh` 一键离线 MOCK 启动；Docker 已弃用并移除 |

## 3. 事实来源优先级（冲突时按此裁决）

```
源码（backend/app/**、frontend/src/**） > 本文档 docs/README.md > docs/SPEC.md > PRD / 架构 / 调研
```

- 源码是最终事实：文档与代码不一致时以代码行为为准，并**修订文档**（不是反过来）。
- Spec 是需求契约：实现未满足 Spec 时，先改代码对齐 Spec；确需改契约时在 Spec §13 追加变更记录。
- 设计 token 以 `frontend/src/design/design-tokens.json` 为唯一来源；`tokens.css` 由它生成，组件零硬编码色。
- 早期顶层 `web/`（设计稿）与 `phase1-tech-research.md`（调研）已移除，不作事实来源。

## 4. API 端点清单（与 Spec §5 一致，含本次补齐项）

| Method | Path | 说明 |
|--------|------|------|
| POST | /documents | 上传 PDF，触发异步索引流水线（202 + document_id + status=queued，带租户/属主/组） |
| GET | /documents | 文档列表（ACL 可见性过滤，含状态/页数/分块数/ACL/版本字段） |
| GET | /documents/{id} | 文档详情 + 分块预览（ACL 过滤，无权限 404） |
| DELETE | /documents/{id} | 删除文档并清理向量/FTS/文件（204；仅属主/管理员） |
| GET | /documents/{id}/file | 取完整原始 PDF（供 pdfjs 加载与 bbox 高亮） |
| POST | /documents/{id}/cancel | 取消摄取（仅瞬态可取消；冲突 409；仅属主/管理员） |
| POST | /documents/{id}/retry | 重试（failed/warning/cancelled 原子认领回 queued，202；原文缺失 409） |
| POST | /documents/{id}/versions | 上传新版本（202 + {document_id, version, status}；仅 active 版本可替换） |
| GET | /documents/{id}/versions | 同 source 全部版本（可见性过滤） |
| GET | /documents/{id}/acl | 取 ACL（{tenant_id, owner_user_id, groups}） |
| PUT | /documents/{id}/acl | 改 ACL（tenant_id 不可修改；仅属主/管理员） |
| POST | /chat | SSE 流式问答（stage/delta/citation/no_answer/done/error 事件；空范围 409） |
| POST | /search | 检索调试（{query, top_k?=5, rerank?=true, document_ids?} → {query, rerank, count, results[]}；范围 ACL 过滤） |
| GET | /config/backends | LLM / Embedding / Rerank 后端就绪状态 |
| GET | /config/settings | 运行时 LLM 配置（backend/base_url/model/api_key_set，key 不回显） |
| PUT | /config/settings | 写运行时 LLM 配置覆盖（持久化即时生效；空串=清除回落 env） |
| POST | /config/reindex | 全量重新索引所有文档（切换嵌入后端/维度变化后需重编码） |
| GET | /health | 健康检查 {status, db, models} |
| GET | /metrics | 可观测指标（计数器 + 直方图 JSON） |
| POST | /feedback | 提交反馈（trace_id + rating/useful + issue_type + 评论；trace 归属校验） |
| GET | /trace/{trace_id} | 管道追踪（evidence/citations/stage_timings/provenance；仅同租户同用户或管理员） |
| POST | /evaluation/run | 运行评测集 → EvaluationReport（默认 profile `public_nist`；未 prepare 409；`synthetic_smoke` 可用） |

## 5. 一致性裁决记录（2026-08-10 文档梳理）

| # | 位置 | 修改前（漂移） | 修改后（裁决值） |
|---|------|----------------|------------------|
| 1 | Spec §5 | API 表缺 `GET /metrics` | 已补（实现/README/DEPLOYMENT 均有） |
| 2 | Spec §5 | /search 请求体 `{query, top_k?}`、响应 `RetrievedChunk[]` | 对齐实现：请求含 rerank/document_ids，响应 `{query, rerank, count, results[]}` |
| 3 | Spec §4 / README / DESIGN.md | vite@^7 | vite@^8（`package-lock.json` 实际锁定 8.2.1） |
| 4 | frontend/package.json | 未显式声明 vite（仅 peer 隐式安装） | 显式声明 `vite@^8.2.1` |
| 5 | DEPLOYMENT.md §5 env 表 | 缺 RAG_EMBED_DIM / RAG_FAISS_TOP_K / RAG_FTS_TOP_K | 已补（与 config.py 对齐） |
| 6 | backend/.env.example | 缺 RAG_FAISS_TOP_K / RAG_FTS_TOP_K | 已补 |
| 7 | 顶层 phase1-tech-research.md | 与 docs/architecture/01-tech-research.md 并存两版 | 顶层标 Superseded，权威版为项目内 |
| 8 | 顶层 web/ 设计稿 | 与 frontend/src/design/ 并存且 wireframes 含 emoji 草稿 | 顶层标 Superseded，权威版为项目内 |
| 9 | 2026-08-10 Docker 实测 | 宿主端口 3000 被本机 open-webui 占用，frontend 起不来 | 改为 3002:80（compose/DEPLOYMENT/README/docs 索引同步）；另发现容器内 Swagger 未反代（nginx 仅 /api/），DEPLOYMENT 注明本地开发访问 :8000/docs |
| 10 | 2026-08-10 F6 原文预览 | 旧按页 `/documents/{id}/pages/{n}` 无法让 pdfjs 获得完整 PDF；真实 Docling 未在首次解析时懒加载，bbox 仍是页面绝对坐标 | 统一为 `/documents/{id}/file`，响应原始字节与上传文件名；首次真实解析先加载 Docling，bbox 按页尺寸和坐标原点转换为 top-left 的 0–1 left/top/right/bottom |
| 11 | 2026-08-12 成熟度扩展：ACL 模型 | 无身份概念，单用户 | `Principal(tenant, user, groups)` + 可见性/管理两级权限，fail-closed（无权限 404/空结果）；管理员 = user_id=admin 或组含 admins；`RAG_TRUSTED_PROXY=true` 才信任反向代理头，CORS 不含 X-Rag-* |
| 12 | 2026-08-12 成熟度扩展：版本策略 | 文档一版本到底 | `source_id + version + is_active + archived_at`；新版本 `version=MAX+1` 原子递增、`is_active=0`，**索引成功才 promote** 归档旧版（失败不替换）；仅 active 版本可发起替换 |
| 13 | 2026-08-12 成熟度扩展：no-answer 语义 | LLM 可能硬答 | 无有效证据 → `no_answer(no_evidence)`（不调 LLM）；有证据但生成无有效引用 → `no_answer(not_supported)`；生成内容整体缓冲，无引用绝不泄出 delta；空知识库 /chat 409 |
| 14 | 2026-08-12 成熟度扩展：trusted-proxy 身份 | 无认证体系 | 身份由可信反向代理注入 X-Rag-* 头（容器 nginx 已注入 default/demo），浏览器无法伪造；生产多租户认证（OIDC）属产品决策，见 MATURITY_MATRIX §3/§11 |
| 15 | 2026-08-12 成熟度扩展：评测 profile 默认值 | 仅内嵌 22 条 mock 语料 | `/evaluation/run` 默认 `public_nist`（真实公开 PDF + 自建 gold，18 题），未 prepare 返回 409；旧 22 条改 `synthetic_smoke`；真实模型适配器 provenance 一律 NOT_RUN，报告确定性自检 |
| 16 | 2026-08-12 成熟度扩展：模型 API 运行时配置 | 前端无配置入口，改后端必须改 env + 重建 | 新增 `GET/PUT /config/settings`（runtime_config 表持久化，覆盖优先于 env，即时生效）；设置页 /settings 落地；API key 明文存本地 SQLite、接口只回显 api_key_set；多租户产品化时收敛为管理员角色（见 MATURITY_MATRIX） |
| 17 | 2026-08-20 解析链路实测 | `parser.py` HybridChunker 将 embed 模型名（Ollama `bge-m3`）当作 HF tokenizer id → 401，真实解析在切块阶段失败 | 改为固定 HF tokenizer `BAAI/bge-m3`，构造纳入 try，异常退回按页切分；Docling 在 WSL 实测通过（NIST AI 100-1/600-1、AI-Agents-in-Depth），结构化分块含 page_no/bbox/section |
| 18 | 2026-08-20 WSL 迁移后文档对齐 | 文档仍以 Docker compose 为部署主路径、端点数为 11/19、目录结构与模型后端未反映 runtime_config 重构，且引用了不存在的 `PRD-文档RAG应用.md`/顶层 `web/`/`phase1-tech-research.md` | 统一为 WSL 原生部署并 delete Docker 遗留（compose/Dockerfile/nginx.conf/scripts-docker/manage.sh）；端点数=22（补 `POST /config/reindex`）；速查表补模型后端三档（mock/http/docling/pdf）与 `runtime_config` 表；目录树、测试数（79）对齐源码 |
| 19 | 2026-08-21 real run provenance 裁决 | `work/public_nist_real_run.json` 的 `reranker_bge: RUN` 与 AGENTS.md 已知薄弱点（bge-reranker 仍为 mock 降级）矛盾；`docling: NOT_RUN` 与 pipeline.name 中 "Docling" 描述不符 | BENCHMARK_CARD 新增 §11 收录 real run 数据并标注 provenance 矛盾；README 简历卡片引用区间值 "recall@5 0.84–0.94" 并标注口径 |
| 20 | 2026-08-21 citation 事件新增检索分数 | citation 事件不含 rrf/faiss/fts 分数，前端无法展示检索融合过程 | citation_service.py 新增 rrfScore/faissScore/ftsScore 字段；CitationPayload/Citation 类型同步；CitationChip tooltip 展示分数 |
| 21 | 2026-08-21 真实模型消融评测收录 | BENCHMARK_CARD §11 real run 归因缺口（embedding vs reranker 贡献不可分）与 AGENTS 薄弱点「bge-reranker 真实权重未测」悬置 | 新增 `real_full_runner.py` 三变体消融（bm25 / hybrid / hybrid+reranker，bge-m3+bge-reranker+真实 LLM 全真实），BENCHMARK_CARD §12 正式收录（recall@5 0.9375 / MRR 0.9062，重排增量 MRR +0.154）；测试数 79→107（新增 test_cache/test_citation 共 28 项）；AGENTS / VALIDATION / MATURITY_MATRIX / REPRODUCE 同步；`work/eval_reports/public_nist_report.json` 于 WSL 复跑再生成（指标与原报告一致） |
| 22 | 2026-08-21 词法 vs 神经重排同口径对比 | §12.4 遗留「词法/神经重排相对优劣」未验证；发现初版 bm25_real_llm 误用 Jaccard 词法重排（口径 bug） | runner 词法重排统一为 `baselines.LexicalReranker`（与生产 mock 同实现），新增 hybrid_lexical_llm 变体并重跑 bm25；结论（BENCHMARK_CARD §12.3）：词法重排在 hybrid 池零增益（MRR 持平 0.752），神经重排 MRR +0.154；bm25 口径修正后与 mock 基线 MRR 0.7469 完全一致（检索确定性跨模型验证） |
| 23 | 2026-08-21 生产切换真实重排 + docling 解析 | 用户要求弃用 mock（词法重排已证零增益）；生产重排存在两处问题：喂给模型的是 200 字符 snippet（信号不足）、候选池为 RRF 融合全量（最多 40 对，CPU 全文 512 token 重排不可用） | runtime_config 切 rerank=bge-reranker-v2-m3 + parse=docling；rerank_service 改为 chunk_repo 回查全文 + 候选截断（`RERANK_CANDIDATES=10`）；core/reranker score 传 `max_length=RERANK_MAX_TOKENS=256`；端到端实测（WSL 热缓存）：检索 2.9s + 重排 7.7s + 生成 12.7s ≈ 23s，引用 page/bbox 正常；新增 test_rerank_service（截断+全文断言），109 passed |

## 6. 文档维护规则（防止再次漂移）

1. **改代码必查速查表**：新增/改名 API、env、指标、DB 字段、状态、模型版本，必须同步本文档 §2/§4 与 Spec。
2. **Spec 契约变更**：在 `docs/SPEC.md` §13 追加记录；禁止静默修改已锁定范围。
3. **设计 token**：只改 `frontend/src/design/design-tokens.json`，`tokens.css` 与组件同步；禁止硬编码 hex 或新增 emoji 图标。
4. **评测集**：增删 `dataset.json` 条目时同步 README 中的条数描述（当前 22 条）。
5. **Superseded 文档**：只加标注不删除；新文档成为权威后必须写明替代关系。
6. **测试门禁**：任何提交前 `backend/` 下 `pytest -q` 必须全绿；前端 `npm run build`（tsc --noEmit）必须通过。

## 7. 目录速览（与源码对应）

```
docrag/
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI 装配 + CORS + 可观测中间件（零业务）
│   │   ├── config.py          # RAG_ 前缀 env（pydantic-settings，唯一配置源）
│   │   ├── db.py              # SQLite 单连接 + asyncio.Lock 写串行（Spec §6）
│   │   ├── schemas.py         # 请求/响应契约（pydantic v2）
│   │   ├── auth.py            # Principal(tenant/user/group) + ACL
│   │   ├── core/              # parser / embeddings / reranker / llm / faiss_store / runtime_config / accelerator / metrics / logging / errors
│   │   ├── repositories/      # document_repo / chunk_repo / trace_repo（数据访问）
│   │   ├── services/          # pipeline / document / index / retrieve / rerank / generate / citation / trace
│   │   ├── routes/            # documents / chat / search / meta / config / trace / evaluation（全部 /api/v1）
│   │   └── evaluation/        # public_runner / real_full_runner / real_llm_runner / public_dataset / eval_metrics / baselines / ablation + datasets/（含 22 条 synthetic dataset.json）
│   ├── requirements*.txt      # 轻量运行时 / 真实模型 / 开发测试 / 评测 四档依赖
│   ├── start_mock.sh          # 一键离线 MOCK 启动（env 全 mock + uvicorn）
│   └── tests/                 # smoke（health/documents）+ 成熟度 + 评测 + cache/citation（107 项）
├── frontend/
│   ├── src/
│   │   ├── pages/             # Home / Documents / Chat / Evaluation / Settings（Spec §7 页面清单）
│   │   ├── components/        # common / layout / ui
│   │   ├── api/ lib/ hooks/   # 请求封装（SSE 手动解析）/ 工具 / 状态
│   │   └── design/            # DESIGN.md + design-tokens.json（双主题 Token 源）
│   └── package.json           # React 19 / Vite 8 / TS 5.6 / Tailwind 4 / Radix / Lucide / pdfjs
├── docs/                      # README(本文) / SPEC / architecture / DEPLOYMENT / ENGINEERING
│                              # + MATURITY_MATRIX / DATA_CARD / BENCHMARK_CARD
│                              #   / EVALUATION_PROTOCOL / REPRODUCE / VALIDATION
└── scripts/evaluation/        # download / prepare / run / gate（评测门禁，CI 与本地通用）
```
