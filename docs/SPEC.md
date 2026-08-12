# Spec - DocRAG（文档 RAG Web 应用）v0.1

> 生成日期：2026-08-07
> 基于：PRD v0.1（许清楚）+ 技术调研 v1（高见远）+ 设计方向 v1 / Phase 2 设计系统（颜好看）
> 状态：已确认（用户 Phase 0/1 已拍板，Phase 1.5 自动生成）
> 性质：规格即契约（Spec as Contract）——后续设计/开发/测试以本文件为唯一依据

---

## 1. 产品定义

- **一句话描述**：一套可私有部署的文档 RAG 应用，用 Docling 保留页码溯源，以「向量 + 关键词」混合检索 + 重排，生成带精准页码引用、可跳转原文 PDF 的回答；默认本地 Ollama、可切 OpenAI 兼容 API。
- **目标用户**：企业知识库管理员 / 合规审查员（P1）、研究者与学生（P2）、开发者与集成方（P3）。
- **核心问题**：让「就 PDF 提问并得到可核实出处」做到精准页码溯源、零依赖部署、中英混合默认可用。

## 2. MVP 范围（锁定——不在此列表的功能一律不做）

| 优先级 | 功能 | 验收标准摘要 | RICE 评分 |
|--------|------|-------------|-----------|
| P0 | F1 PDF 上传 + Docling 解析（保留 page_no/章节/bbox 溯源） | 上传可提取文本 PDF 后，每块含 page_no 与溯源元数据且可预览 | 6.0 |
| P0 | F2 结构化分块（HybridChunker，写 page_no+bbox+section） | 按标题/段落/表格边界切分，不暴力截断，每块带元数据 | 6.67 |
| P0 | F3 混合检索（FAISS 稠密 + FTS5 关键词，RRF 融合） | 同时走两路并融合，返回 Top-K | 6.0 |
| P0 | F4 Rerank（bge-reranker-v2-m3，默认开不可降级） | top-20 → top-5 精排，默认开启 | 4.8 |
| P0 | F5 带页码引用回答（双后端 Ollama/OpenAI，env 切换） | 回答含 [页码] 标记，后端可切换 | 7.5 |
| P0 | F6 PDF 原文预览 + 引用高亮跳转 | 点击引用跳页并高亮 bbox 区域 | 6.08 |
| P0 | F7 多语言默认嵌入（bge-m3 dense+sparse） | 中英混排开箱可用，无需手动换模型 | 8.0 |
| P1 | F8 Docker 零外部依赖部署 | 一条 compose 起全套，无外部服务依赖 | 4.8 |
| P1 | F9 基础评测集 + 评测脚本 | ≥20 条问答 + 标准出处，输出引用准确率/召回率 | 3.2 |
| P1 | F10 多文档管理（上传列表/删除/状态） | 增删文档同步索引与 FTS/向量清理 | 2.1 |

## 3. 明确不做（Out-of-Scope — 锁定）

| 不做的功能 | 原因 | 何时考虑 |
|------------|------|----------|
| 用户认证与多租户权限隔离 | MVP 单用户/本地优先，复杂度高 | v2.0 |
| 知识图谱 / GraphRAG | 跨文档多跳非 MVP 目标 | v2.0+ |
| 多轮 Agent / 工具调用 | 超出问答核心链路 | 后续阶段 |
| 扫描件深度 OCR | MVP 聚焦可提取文本 PDF | Docling easyocr extra 后续 |
| 移动端原生 App | 先做 Web | 后续 |
| 语音/播客式输出 | 非核心 | 后续 |

## 4. 技术架构（锁定 — 含版本锚定）

| 层 | 技术 | 实际版本（锁定） | 锁定原因 |
|----|------|----------|----------|
| 前端框架 | React + Vite + TS | react@^19, vite@^8, typescript@^5.6 | SPA 无需 SSR，RAG 生态最全 |
| 前端样式 | Tailwind CSS 4 + Radix UI | tailwindcss@^4, @radix-ui/*@^1 | 暗色主题低成本，无障碍原语 |
| 前端状态 | TanStack Query + Zustand | @tanstack/react-query@^5, zustand@^5 | 服务端状态 + UI 状态分离 |
| 前端图标 | **Lucide（lucide-react）** | lucide-react@^1.24.0 (ISC) | P0 锁定单一 SVG 库，禁 emoji |
| PDF 预览 | pdfjs-dist | pdfjs-dist@^6.0.0 (Apache-2.0) | 前端渲染 + bbox 视口映射高亮 |
| 后端框架 | FastAPI | fastapi==0.115.13, pydantic>=2.11,<3 | 异步长任务 + 自动 OpenAPI |
| ASGI 服务 | Uvicorn + Gunicorn | uvicorn>=0.30, gunicorn>=22 | 生产多 worker |
| 配置 | pydantic-settings | >=2.3 | env 注入全部可调项 |
| 解析 | docling | docling==2.117.0 (+ HybridChunker) | prov 天然含 page_no+bbox |
| 嵌入 | FlagEmbedding (bge-m3) | flag-embedding>=1.3, BAAI/bge-m3 | dense(1024)+sparse 一体，100+语言 |
| 重排 | sentence-transformers (bge-reranker-v2-m3) | >=3.3, BAAI/bge-reranker-v2-m3 | 多语言 CrossEncoder，本地零成本 |
| 向量 | FAISS | faiss-cpu==1.14.3 | IndexFlatIP 归一化=cosine，零服务 |
| 关键词 | SQLite FTS5 | trigram tokenizer | 中英子串匹配，零依赖 |
| 元数据/FTS | SQLite | 3.34+ 内置 FTS5 | 单文件、零服务 |
| LLM | openai SDK（双后端抽象） | openai>=1.40 | base_url 切换 Ollama/OpenAI，零分支 |
| 部署 | Docker + docker-compose | - | 单 compose 起前后端全链路 |
| 运行环境 | Python | >=3.10，推荐 3.11 | Docling 2.x 弃用 3.9 |

**双后端抽象（LLM）env 契约**：
- `RAG_LLM_BACKEND=ollama|openai`（默认 ollama）
- `RAG_OLLAMA_BASE_URL=http://localhost:11434/v1`
- `RAG_OPENAI_BASE_URL=`、`RAG_OPENAI_API_KEY=`、`RAG_LLM_MODEL=`

**模型获取策略（部署约束）**：模型权重（bge-m3 ~2.2GB/int8 量化570MB、reranker 568MB）运行时挂载 volume + 首次自动拉取（HuggingFace / Ollama），镜像保持精简；部署文档明示最低配置 ≥8GB RAM、≥10GB 空闲磁盘。

## 5. API 端点清单（锁定——开发时以此为唯一依据）

所有接口前缀 `/api/v1`。认证暂不做（MVP 单用户；身份经可信反向代理注入的 `X-Rag-Tenant/User/Group` 头解析，见 §13 记录 2026-08-12-1）。

| Method | Path | 功能 | 认证 | 请求体 | 响应体 |
|--------|------|------|------|--------|--------|
| POST | /documents | 上传 PDF，触发解析+分块+索引流水线 | 否 | multipart: file | 202 + document_id + 初始状态 |
| GET | /documents | 文档列表（含状态/页数/分块数） | 否 | - | Document[] |
| GET | /documents/{id} | 文档详情 + 分块预览 | 否 | - | Document + Chunk[] |
| DELETE | /documents/{id} | 删除文档并清理向量/FTS | 否 | - | 204 |
| GET | /documents/{id}/file | 取完整原始 PDF（供 pdfjs 加载与 bbox 高亮） | 否 | - | application/pdf 文件流（原上传文件名） |
| POST | /chat | 问答（SSE 流式，带引用） | 否 | {query, document_ids?, rerank?:bool} | text/event-stream（delta + citation 事件） |
| POST | /search | 检索调试（非流式，返回候选+分数） | 否 | {query, top_k?(默认5), rerank?(默认true), document_ids?} | {query, rerank, count, results[]} |
| GET | /config/backends | 双后端状态（LLM/Rerank/Embedding 是否就绪） | 否 | - | BackendStatus |
| GET | /health | 健康检查 | 否 | - | {status, db, models} |
| GET | /metrics | 可观测指标（计数器 + 延迟直方图，JSON） | 否 | - | {counters, histograms, generated_at} |
| POST | /evaluation/run | 运行评测集 | 否 | {config?} | EvaluationReport（默认 profile `public_nist`；未 prepare 409） |
| POST | /documents/{id}/cancel | 取消摄取（仅瞬态可取消；冲突 409） | 否 | - | StatusOut |
| POST | /documents/{id}/retry | 重试（failed/warning/cancelled 原子认领回 queued；202） | 否 | - | StatusOut |
| POST | /documents/{id}/versions | 上传新版本（仅 active 版本可替换；202） | 否 | multipart: file | VersionCreateOut |
| GET | /documents/{id}/versions | 同 source 全部版本（可见性过滤） | 否 | - | Document[] |
| GET | /documents/{id}/acl | 取 ACL（{tenant_id, owner_user_id, groups}） | 否 | - | AclPayload |
| PUT | /documents/{id}/acl | 改 ACL（tenant_id 不可修改；仅属主/管理员） | 否 | AclPayload | AclPayload |
| POST | /feedback | 提交反馈（trace 归属校验） | 否 | {trace_id, rating/useful, issue_type?, selected_text?, comment?} | {ok: true} |
| GET | /trace/{trace_id} | 管道追踪（仅同租户同用户或管理员） | 否 | - | TraceOut |

**SSE 事件协议（/chat）**：
- `event: stage` → `{stage: retrieving|reranking|generating}`（阶段开始）
- `event: delta` → `{text}` 回答文本增量（先缓冲校验存在有效引用后再泄出）
- `event: citation` → `{index, docId, docName, page, bbox?, snippet?, sourceId?, version?, title?, createdAt?, processingMs?}`（与 F6 透传契约一致）
- `event: no_answer` → `{reason: no_evidence|not_supported, evidence_candidates}`（仅无有效证据时发，之前不得有 delta/citation）
- `event: done` → `{selected_document_ids, trace_id}`
- `event: error` → `{message}`

**文档状态枚举（/documents）**：`queued / parsing / chunking / embedding / indexed / warning / failed / cancelled`（warning=部分阶段成功、分块保留可检索；failed/cancelled 为终态；cancel/retry 走原子认领；服务重启时瞬态 → failed，reason=`service_restart_interrupted`）。

## 6. 数据库表清单（锁定）

单 SQLite 库 `app.db`。

| 表名 | 核心字段 | 索引 | 关联 |
|------|----------|------|------|
| documents | id, filename, sha256, page_count, status(queued/parsing/chunking/embedding/indexed/warning/failed/cancelled), error, created_at, **tenant_id, owner_user_id, group_ids, source_id, version, is_active, archived_at**（成熟度：ACL 与生命周期，旧库由 `_migrate` 补列） | idx_documents_status, idx_documents_source, idx_documents_tenant | 1:N chunks |
| chunks | id, document_id, seq, content, page_no(必带), bbox(text JSON, 可选), section, embedding(BLOB float32 1024维), created_at | idx_chunks_doc, idx_chunks_page | N:1 documents |
| chunk_fts | FTS5 虚拟表 on content, content_rowid=chunks.id, tokenize='trigram' | - | 1:1 chunks |
| evaluations | id, run_at, config_json, metrics_json | - | - |
| document_events | id, document_id, source_id, version, from_status, to_status, reason, created_at, is_transient（状态流转审计） | idx_events_doc | N:1 documents |
| trace | trace_id, created_at, tenant_id, user_id, query_hash(固定 not_stored，query 原文不落库), status, rerank_used, selected_document_ids, evidence, citations, stage_timings, model_provenance, error_message | idx_trace_owner | 1:N feedback |
| feedback | id, trace_id, rating, issue_type, selected_text, comment, created_at | - | N:1 trace |

**索引写入并发控制**：SQLite 写用单连接 + 进程内 asyncio.Lock，防止并发损坏。
**F6 溯源契约（硬约束）**：`chunks.page_no` 必填；`chunks.bbox` 存 Docling 归一化坐标 JSON（left/top/right/bottom，可空）；评测/预览均以此为准。

## 7. 页面清单（锁定）

| 页面 | 路由 | 核心组件 | 对应 API | 设计 Token 主题 |
|------|------|----------|----------|-----------------|
| 概览/首页 | / | UploadDropzone, RecentDocs, RecentChats, SystemStatus | /documents | dark 默认 + light |
| 文档管理 | /documents | DocTable(三态), DocDrawer, EmptyState | /documents, DELETE | dark/light |
| 问答（签名页） | /chat | ChatPanel, MessageBubble, CitationChip, PDFPreview(pdfjs), BackendSelector, Stepper | /chat, /search, /documents/{id}/file | dark/light（PDF 暗色 chrome） |
| 评测 | /evaluation | EvalConfig, EvalReportCard | /evaluation/run | dark/light |

**布局**：问答页为三栏工作区（文档面板 | 对话区 | PDF 预览）。

## 8. 设计 Token（锁定）

> 来源：Phase 2 `design-tokens.json`（已落盘 `frontend/src/design/`）。前端 `import` 即用，组件零硬编码色（仅 `#fff`/`#000` 例外）。

- **主题**：dark 默认 + 完整 light 第二主题（`data-theme` 切换）。
- **主色**：`--accent` `#3E63DD`（精炼靛蓝，避开 Tailwind 默认 AI 模板味）；禁止紫粉渐变。
- **签名色**：`--citation` `#F5B544`（琥珀，专用于 PDF 页码引用高亮），与 accent 冷暖对比。
- **中性**：`--bg` `#0B0D10` / `--surface` `#131619` / `--fg` `#ECEEF1`（dark）；`--bg` `#F9FAFB` / `--surface` `#FFFFFF` / `--fg` `#111827`（light）。
- **语义**：success `#3FB950`、warn `#E8833A`、danger `#F85149`。
- **字体**：`--font-display` Inter + Noto Sans SC；`--font-mono` JetBrains Mono。字重 400/510/590。
- **图标库**：Lucide（lucide-react），尺寸 16/20/24px，统一 currentColor，**全项目禁 emoji（P0）**。
- **间距**：4px 网格（4/8/12/16/24/32/40/48/64/80）。圆角 6/12/16/pill。
- **运动**：150ms 功能动效；支持 prefers-reduced-motion。

## 9. 验收标准（锁定——QA 测试时以此为唯一依据，EARS 格式）

| 编号 | 功能 | EARS 格式验收标准 | 优先级 |
|------|------|-------------------|--------|
| AC-01 | 上传解析 | When 用户上传可提取文本 PDF，系统**必须**在状态变为 indexed 后使每块携带 page_no 与溯源元数据 | P0 |
| AC-02 | 结构化分块 | While 分块完成，系统**必须**按标题/段落/表格边界切分而非固定字符截断 | P0 |
| AC-03 | 混合检索 | When 用户提问，系统**必须**同时执行 FAISS 稠密与 FTS5 关键词两路并用 RRF(k=60) 融合，返回 Top-K | P0 |
| AC-04 | Rerank | If rerank 开启（默认），系统**必须**对 top-20 用 bge-reranker-v2-m3 精排取 top-5 | P0 |
| AC-05 | 带引回答 | When 生成回答，系统**必须**在回答中附 [页码] 引用且每个引用可映射到 chunk.page_no | P0 |
| AC-06 | PDF 高亮 | When 用户点击引用，系统**必须**打开对应 PDF 页并在 bbox（若有）区域叠加琥珀高亮 | P0 |
| AC-07 | 双后端 | If `RAG_LLM_BACKEND=openai` 且配置 endpoint，系统**必须**走 OpenAI 兼容 API 生成带引用回答 | P0 |
| AC-08 | 多语言 | When 知识库含中英混排文档，系统**必须**用 bge-m3 召回对应段落并给出页码 | P0 |
| AC-09 | Docker | When 执行 `docker compose up`，系统**必须**自包含启动前后端全链路且无外部服务依赖 | P1 |
| AC-10 | 评测 | When 运行评测脚本，系统**必须**输出引用准确率/召回@K 报告 | P1 |
| AC-11 | 删除同步 | When 删除文档，系统**必须**清理对应向量 BLOB 与 FTS 条目 | P1 |
| AC-12 | 空状态 | While 知识库无文档，系统**必须**禁用问答并提示"请先上传文档" | P1 |
| AC-13 | P0 视觉 | While 渲染任意页面，系统**必须不**出现 emoji 功能图标、紫粉渐变、硬编码色 | P0 |

## 10. 边界与约束

- 不支持 IE；兼容现代 Chrome/Safari/Firefox 最新 2 版。
- 响应式断点：≥1280 三栏 / 768–1279 双栏可折叠 / <768 单栏堆叠。
- 性能目标：≤100 页 PDF 解析 <3min；问答首响（非首次模型加载）<8s。
- 单 PDF >100 页给出分块数预估与耗时提示；空查询不触发检索。
- 索引写入加锁防并发损坏 SQLite；密钥/端点不入库。
- 默认 Ollama 后端完全离线；OpenAI 兼容后端需联网，失败明确报错。

## 11. 内嵌已知坑（从团队记忆拉取——首次项目，写入基线风险）

| 坑 | 技术栈指纹 | 根因 | 修法 |
|----|------------|------|------|
| FastAPI/Pydantic /docs 500 | fastapi<0.115 + pydantic 2.11.7 | 版本兼容坑 | 锁定 fastapi==0.115.13 + pydantic>=2.11 |
| FTS5 trigram 短中文无召回 | sqlite fts5 trigram | 需≥3连续字符 | 1–2 字中文走 LIKE 兜底 / 加载 trigram 增强扩展 |
| pdfjs worker 未配置 | pdfjs-dist@^6 | v4+ 必须配 worker | 经 `?url` 引入 GlobalWorkerOptions.workerSrc；旧 bundler 加 Promise.withResolvers polyfill |
| Docling 扫描件溯源偏移 | docling + 布局模型 | 复杂多栏/跨页表格 | OCR extra 兜底 + 评测集覆盖 |
| bge-m3 首次权重大/CPU 慢 | flag-embedding bge-m3 | 2.2GB/量化570MB | int8 量化 + 运行时挂载 volume |

## 12. 端到端验证步骤（Spec 锁定的最后一项）

```bash
# 1. 构建并启动（零外部依赖）
docker compose up --build

# 2. 健康检查
curl http://localhost:8000/api/v1/health
# 断言：{"status":"ok","db":true,"models":{"embed":"ready"|"loading"}}

# 3. 上传 PDF 并触发索引
curl -F "file=@sample.pdf" http://localhost:8000/api/v1/documents
# 断言：202 + document_id；轮询 GET /documents 至 status=indexed

# 4. 核心成功流（流式问答 + 引用）
curl -N -X POST http://localhost:8000/api/v1/chat -H "Content-Type: application/json" \
  -d '{"query":"本文档第三章的主要结论是什么？"}'
# 断言：收到 citation 事件含 page 字段；delta 文本含 [n] 标记

# 5. 双后端切换验证
RAG_LLM_BACKEND=openai RAG_OPENAI_BASE_URL=... RAG_OPENAI_API_KEY=... docker compose up
curl -N -X POST http://localhost:8000/api/v1/chat -d '{"query":"测试问题"}'
# 断言：走 OpenAI 兼容端点返回带引用回答

# 6. 评测
curl -X POST http://localhost:8000/api/v1/evaluation/run
# 断言：返回引用准确率/召回@K 报告
```

## 13. 变更记录

| 日期 | 变更内容 | 原因 | 影响范围 |
|------|----------|------|----------|
| 2026-08-07 | 初始 Spec v0.1 生成 | Phase 1 三文档确认并补充工程说明 | 全范围锁定 |
| 2026-08-07 | 新增 ENGINEERING.md | 汇总关键决策、验证边界与路线图 | 文档结构 |
| 2026-08-10 | 0 歧义梳理（docrag/docs/README.md §5 裁决记录） | 文档与代码漂移修复：§5 API 表补 /metrics、/search 请求体对齐、vite@^7→^8（lock 实际 8.2.1） | Spec §4/§5 |
| 2026-08-10 | F6 原文预览闭环 | 整文档 `/documents/{id}/file` 取原始 PDF；首次真实解析懒加载 Docling，bbox 按对应页尺寸和坐标原点统一为 top-left 的归一化 left/top/right/bottom | Spec §5/§6、解析器、前端 PDFPreview |
| 2026-08-12-1 | 契约扩展：文档生命周期与版本 | 新增 `POST/DELETE …/cancel`、`…/retry`、`POST/GET …/versions`；documents 表新增 source_id/version/is_active/archived_at 与 document_events 审计表；状态枚举增加 warning/cancelled | Spec §5/§6 |
| 2026-08-12-2 | 契约扩展：ACL 与身份 | 新增 `GET/PUT …/acl`；身份经可信反向代理 `X-Rag-Tenant/User/Group` 头注入（`RAG_TRUSTED_PROXY=true` 才解析，CORS 不允许浏览器携带）；可见性/管理两级权限 fail-closed | Spec §5（认证栏）、§6 documents 列 |
| 2026-08-12-3 | 契约扩展：无答案与证据事件 | /chat SSE 新增 `stage`、`no_answer`（no_evidence/not_supported）事件；citation 事件扩展 sourceId/version/title/createdAt；生成内容缓冲校验（无有效引用不泄出 delta）；空知识库 /chat 409 | Spec §5 SSE 协议 |
| 2026-08-12-4 | 契约扩展：反馈与追踪 | 新增 `POST /feedback`、`GET /trace/{trace_id}`；trace/feedback 表；query 原文与可反查哈希不落库（query_hash 固定 not_stored）；trace 按租户/用户 ACL 过滤 | Spec §5/§6 |
| 2026-08-12-5 | 契约扩展：版本化评测 | `/evaluation/run` 默认 profile `public_nist`（NIST 公开 PDF + 自建 gold，18 题；未 prepare 返回 409）；旧 22 条内嵌问答归 `synthetic_smoke`；报告含 CI/切片/per-query/provenance；真实模型适配器 NOT_RUN；基准详情见 docs/BENCHMARK_CARD.md | Spec §5 |
| 2026-08-12-6 | 契约扩展：运行时模型配置 | 新增 `GET/PUT /config/settings`：LLM 后端/base_url/model/api_key 运行时覆盖（runtime_config 表持久化，覆盖优先于 env 默认，即时生效无需重启；API key 明文存本地 SQLite 且接口只回传 api_key_set）；设置页落地（/settings）；多租户产品化时应收敛为管理员角色 | Spec §5/§6 |
