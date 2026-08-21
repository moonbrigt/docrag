# DocRAG 部署文档

本文覆盖从零到可访问的完整部署路径：WSL 原生存启动、环境变量、从 MOCK 切换到真实模型、可观测端点与生产加固建议。运行环境唯一为 **WSL（Ubuntu）**；Docker 已弃用并移除。

---

## 1. 前置要求（WSL 原生）

| 项目 | 说明 |
|------|------|
| WSL | Ubuntu 发行版，项目位于 `/home/z1050/Projects/docrag` |
| Python | 3.12（后端 venv `backend/.venv` 已建） |
| Node | nvm 管理（v24）；需先 `source ~/.nvm/nvm.sh` |
| 内存 | MOCK 演示 ≥ 2 GB；真实模型（bge-m3 ~2.2GB/量化 570MB + reranker 568MB）建议 ≥ 8 GB |
| 磁盘 | MOCK ≥ 2 GB；真实模型含权重 ≥ 10 GB 空闲 |
| 网络 | MOCK 模式完全离线；真实模型首次运行需联网拉取权重 |

---

## 2. 启动（默认 MOCK，离线可跑）

```bash
cd /home/z1050/Projects/docrag

# 一键离线 MOCK 启动（backend/ 下；把 runtime_config 与 env 全部置为 mock）
cd backend && ./start_mock.sh        # http://localhost:8000

# 或手动启动（模型后端以设置页 runtime_config 为准）
cd backend && ./.venv/bin/python -m uvicorn app.main:app --port 8000

# 前端（另开终端，frontend/ 下）
cd frontend && source ~/.nvm/nvm.sh && npm run dev   # http://localhost:5173（/api 代理到 8000）
```

- 后端 API：http://localhost:8000/api/v1/health
- Swagger：http://localhost:8000/docs
- 前端生产构建：`npm run build`（tsc --noEmit + vite build）

默认 `RAG_*_MOCK=true`，所有重模型（解析/嵌入/重排/LLM）走确定性 mock，**无需下载任何大模型权重即可端到端体验上传→解析→问答→引用高亮**的完整链路。MOCK 无模型权重落地；真实模型数据（SQLite + PDF 原件）在项目目录由 `RAG_DATA_DIR`/`RAG_DB_PATH` 指定。

---

## 3. 切换到真实模型（生产 / 高质量检索）

### 3.1 启动前 env 关闭 MOCK

在启动后端前设置环境变量，关闭 MOCK 并指定真实后端：

```bash
export RAG_LLM_MOCK=false
export RAG_EMBED_MOCK=false
export RAG_RERANK_MOCK=false
export RAG_PARSE_MOCK=false
export RAG_LLM_BACKEND=ollama        # 或 openai
export RAG_OLLAMA_BASE_URL=http://localhost:11434/v1
export RAG_LLM_MODEL=qwen3:4b
```

> **运行时切换（无需改 env / 重启）**：`/config/settings`（设置页）支持对 LLM（`llm`）、嵌入（`embed`）、重排（`rerank`）、解析（`parse`）的 `backend` 与 `model` 做运行时覆盖，持久化到本地 SQLite `runtime_config` 表，即时生效。生效优先级：运行时覆盖 > 环境变量默认。

**切换嵌入后端/模型后**，已持久化向量的维度或空间可能不同，需在设置页点「重新索引全部文档」（`POST /config/reindex`）对全库重编码；既有文档需重上传才能正确检索。

### LLM 后端说明

默认 **mock**（离线、确定性流式、不下载权重）；启用真实后端后再按下面两种切换：

- **Ollama**：宿主机（WSL）运行 Ollama 并 `ollama pull <model>`，`RAG_OLLAMA_BASE_URL` 指向其 `/v1` 端点（免密钥，本地零成本）。
- **OpenAI 兼容**：设 `RAG_LLM_BACKEND=openai`，填 `RAG_OPENAI_BASE_URL` 与 `RAG_OPENAI_API_KEY`，模型名 `RAG_LLM_MODEL`。统一 openai SDK + base_url，无需改代码。

### 真实模型选项（后端 `Literal` 契约）

| 模块 | 后端选项 | 说明 |
|------|----------|------|
| 解析 | `docling` / `pdf` / `mock` | docling=DocumentConverter+HybridChunker（page_no+bbox）；pdf=pypdf 轻量按页 |
| 嵌入 | `bge-m3` / `http` / `mock` | bge-m3=FlagEmbedding 本地；http=OpenAI 兼容 `/v1/embeddings`（需自备 key） |
| 重排 | `bge-reranker-v2-m3` / `mock` | CrossEncoder 本地 / mock 词重叠 |
| LLM | `ollama` / `openai` / `mock` | openai SDK + base_url |

---

## 4. 环境变量一览（均带 `RAG_` 前缀）

| 变量 | 默认 | 说明 |
|------|------|------|
| RAG_DATA_DIR | ./data | 上传 PDF 与 SQLite 存放目录 |
| RAG_DB_PATH | ./app.db | SQLite 文件路径 |
| RAG_MODEL_DIR | ./models | 模型权重目录 |
| RAG_EMBED_BACKEND | bge-m3 | 嵌入后端（bge-m3 / http / mock） |
| RAG_EMBED_MODEL | BAAI/bge-m3 | 嵌入模型名 |
| RAG_EMBEDDING_ENDPOINT | （空） | http 嵌入后端端点 |
| RAG_EMBEDDING_API_KEY | （空） | http 嵌入 API Key |
| RAG_EMBED_MOCK | true | 嵌入走确定性 mock（离线） |
| RAG_EMBED_DIM | 1024 | 嵌入向量维度（切换模型需重索引） |
| RAG_RERANK_BACKEND | bge-reranker-v2-m3 | 重排后端（bge-reranker-v2-m3 / mock） |
| RAG_RERANK_MOCK | true | 重排走 mock |
| RAG_PARSE_BACKEND | docling | 解析后端（docling / pdf / mock） |
| RAG_PARSE_MOCK | true | 解析走 mock |
| RAG_LLM_BACKEND | ollama | LLM 后端（ollama / openai / mock） |
| RAG_LLM_MOCK | true | LLM 走 mock |
| RAG_OLLAMA_BASE_URL | http://localhost:11434/v1 | Ollama 的 OpenAI 兼容端点 |
| RAG_OPENAI_BASE_URL | （空） | OpenAI 兼容端点 |
| RAG_OPENAI_API_KEY | （空） | API Key |
| RAG_LLM_MODEL | llama3.1:8b | 生成模型名 |
| RAG_ACCELERATOR | auto | 计算加速（auto / cuda / cpu） |
| RAG_RRF_K | 60 | RRF 融合常数 |
| RAG_RETRIEVE_TOP_K | 20 | RRF 融合前的每路候选数 |
| RAG_FAISS_TOP_K | 20 | FAISS 稠密路候选数 |
| RAG_FTS_TOP_K | 20 | FTS5 关键词路候选数 |
| RAG_RERANK_TOP_K | 5 | 重排后保留数 |
| RAG_CACHE_TTL | 300 | hybrid_retrieve 结果缓存 TTL（秒），0=禁用 |
| RAG_TRUSTED_PROXY | false | true 时信任反向代理注入的 X-Rag-Tenant/User/Group 头解析身份（ACL 依赖） |
| RAG_PORT | 8000 | 后端监听端口 |

> env 默认均可被设置页 `runtime_config` 运行时覆盖。

---

## 5. 可观测端点

| 端点 | 用途 |
|------|------|
| `GET /api/v1/health` | DB 连通性 + 各模型就绪状态；`status: ok/degraded` |
| `GET /api/v1/config/backends` | LLM / Embedding / Rerank 后端类型与就绪详情 |
| `GET /api/v1/metrics` | 进程内计数器 + 延迟直方图（JSON），可接入 Prometheus |
| 日志 | 后端 JSON 单行日志（含请求方法/路径/状态码/耗时） |

计数器：`document_uploads_total` / `documents_indexed_total` / `documents_failed_total` / `queries_total` / `citations_returned_total` / `errors_total`；直方图：`http_request_latency_ms` / `pipeline_latency_ms` / `retrieve_latency_ms` / `llm_latency_ms`。

---

## 6. 评测运行

- Web：进入「评测」页 → 选择 profile（默认 `public_nist`）→ 点击「运行评测」。
- 公开评测（默认，真实公开 PDF + 自建 gold，18 题）：

```bash
bash scripts/evaluation/prepare.sh      # 下载+校验 NIST PDF（SHA-256）→ 构建语料 → 验证 gold（fail-closed）
bash scripts/evaluation/run.sh          # 确定性基线评测 → work/eval_reports/public_nist_report.json
```

- 旧内嵌 22 条手写问答为 `synthetic_smoke` profile：`cd backend && ./.venv/bin/python -m app.evaluation.runner`，或评测页选择该 profile。
- `POST /api/v1/evaluation/run` 未 prepare 时返回 **409** 并提示先运行 `scripts/evaluation/prepare.sh`。
- 指标口径、CI 与 provenance 说明见 `docs/BENCHMARK_CARD.md`、`docs/EVALUATION_PROTOCOL.md`；真实模型适配器（bge-m3/reranker/LLM）多为 NOT_RUN，真实部署下交换机后需重新评测并更新 provenance。

---

## 7. 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 问答返回 503「模型未就绪」 | 真实后端未启用或权重未下载 / 不可达 | 确认 `*_MOCK=false` 且模型已就绪；或临时改回 MOCK |
| 解析失败「文件可能加密/损坏」 | 加密 PDF 或 Docling 不支持 | 用户提供非加密 PDF；检查 backend 日志 |
| 引用跳转不到页 | 该引用未携带 `bbox` | 前端降级为整页高亮；确认后端 chunk 透传 `bbox` |
| 前端白屏 | 后端未起 / Vite 代理目标不对 | 确认 `/api/v1/health` 可访问；开发由 Vite 代理 `/api` 到 8000 |
| 评测接口返回 409 | `public_nist` 未 prepare（无 `work/eval_corpus.json`）或语料与 manifest 版本不符 | 先运行 `scripts/evaluation/prepare.sh` 后重试；语料版本不符时删除 `work/eval_corpus.json` 重新 prepare |
| 切换嵌入模型后检索错乱 | 向量维度/空间变化，旧文档未重编码 | 设置页「重新索引全部文档」（`POST /config/reindex`）；更换向量维度前务必重索引 |
| 问答返回 409「知识库为空」 | 当前身份无可见文档或显式空范围 | 上传文档或调整 ACL 后重试（见 MATURITY_MATRIX §3） |

---

## 8. 生产加固建议（非 MVP 必做，供参考）

- 多租户生产：在网关层接入 OIDC/企业 IdP，认证后注入 `X-Rag-*` 身份头（后端不内置认证；`RAG_TRUSTED_PROXY=true` 且仅允许经可信代理访问后端）。
- 后端置于私有网络，仅暴露 `/api`；启用速率限制与输入校验（代码已含基础校验）。
- 模型权重预置于本地模型目录，避免运行时外网拉取。
- 将 `/api/v1/metrics` 接入 Prometheus + Grafana；日志接入集中式采集。
- 大语料（>100 万 chunk）时 FAISS 由 IndexFlatIP 升级为 IVF/PQ（代码预留切换点）。