# DocRAG 部署文档

本文覆盖从零到可访问的完整部署路径：Docker 一键部署（推荐）、本地开发、环境变量、从 MOCK 切换到真实模型、可观测端点与生产加固建议。

---

## 1. 前置要求

| 项目 | 说明 |
|------|------|
| Docker / Docker Compose | 任意较新版本（Compose v2：命令为 `docker compose`） |
| 内存 | MOCK 演示 ≥ 2 GB；真实模型（bge-m3 ~2.2GB / 量化 570MB + reranker 568MB）建议 ≥ 8 GB |
| 磁盘 | MOCK ≥ 2 GB；真实模型含权重 ≥ 10 GB 空闲 |
| 网络 | MOCK 模式完全离线；真实模型首次运行需联网拉取权重（或挂载预置模型目录） |

---

## 2. Docker 一键部署（默认 MOCK，离线可跑）

```bash
cd docrag
docker compose up --build
```

- 前端：http://localhost:3002 （nginx 托管 SPA 并反代 `/api` 到 backend；3000 常被占用故用 3002）
- 后端 API：http://localhost:3002/api/v1/health
- 交互式文档（Swagger）：容器内未反代 `/docs`，本地开发用 `uvicorn app.main:app` 后访问 http://localhost:8000/docs

`docker-compose.yml` 中 backend 的环境变量默认将 `RAG_*_MOCK` 设为 `true`，所有重模型（解析/嵌入/重排/LLM）走确定性 mock，因此**无需下载任何大模型权重即可端到端体验上传→解析→问答→引用高亮**的完整链路（评测集同理离线可复现）。

数据与模型分别挂载在命名卷 `docrag_data`（SQLite + 上传 PDF）与 `docrag_models`（模型权重）中，容器重建不丢数据。

停止：`docker compose down`（保留卷）；彻底清理：`docker compose down -v`。

---

## 3. 切换到真实模型（生产 / 高质量检索）

编辑 `docker-compose.yml`，将 backend 的 `RAG_*_MOCK` 全部改为 `"false"`：

```yaml
environment:
  RAG_LLM_MOCK: "false"
  RAG_EMBED_MOCK: "false"
  RAG_RERANK_MOCK: "false"
  RAG_PARSE_MOCK: "false"
  RAG_LLM_BACKEND: "ollama"        # 或 openai
  RAG_OLLAMA_BASE_URL: "http://host.docker.internal:11434/v1"
  RAG_LLM_MODEL: "llama3.1:8b"
```

并在 `volumes` 中为 backend 挂载宿主模型目录（或允许容器内首次运行时自动从 HuggingFace 下载到 `docrag_models` 卷）：

```yaml
volumes:
  - docrag_models:/models
```

> **镜像默认只装「轻量运行时」**（`requirements.txt`），不含 torch / docling / sentence-transformers 等重依赖，以减小体积、加快构建。切真实模型前需先把重依赖装进容器：
>
> ```bash
> docker compose exec backend pip install -r requirements-ml.txt
> ```
> 或在 Dockerfile 末尾追加 `RUN pip install -r requirements-ml.txt` 后 `docker compose up --build --build-arg ...`。

重新构建并启动：`docker compose up --build`。

### LLM 双后端说明
- **Ollama（默认）**：宿主机运行 Ollama 并 `ollama pull llama3.1:8b`，`RAG_OLLAMA_BASE_URL` 指向其 `/v1` 端点（容器内访问宿主用 `host.docker.internal`）。
- **OpenAI 兼容**：设 `RAG_LLM_BACKEND=openai`，填 `RAG_OPENAI_BASE_URL` 与 `RAG_OPENAI_API_KEY`，模型名 `RAG_LLM_MODEL`。无需改动代码（统一 openai SDK + base_url）。

---

## 4. 本地开发部署

### 后端
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env          # 离线演示：将 *_MOCK 改为 true
uvicorn app.main:app --reload --port 8000
```
健康检查：`curl http://localhost:8000/api/v1/health`

### 前端
```bash
cd frontend
npm install
npm run dev                    # http://localhost:5173（Vite 代理 /api 到 8000）
# 生产构建：npm run build && npm run preview
```
前端以相对路径 `/api/v1` 调用后端；生产由 nginx 反代，开发由 Vite 代理，二者均无需在前端硬编码后端地址。

---

## 5. 环境变量一览（均带 `RAG_` 前缀）

| 变量 | 默认 | 说明 |
|------|------|------|
| RAG_DATA_DIR | ./data | 上传 PDF 与 SQLite 存放目录 |
| RAG_DB_PATH | ./app.db | SQLite 文件路径 |
| RAG_MODEL_DIR | ./models | 模型权重目录 |
| RAG_EMBED_BACKEND | bge-m3 | 嵌入后端（bge-m3 / mock） |
| RAG_EMBED_MOCK | false | 嵌入走确定性 mock（离线） |
| RAG_EMBED_DIM | 1024 | 嵌入向量维度 |
| RAG_RERANK_MOCK | false | 重排走 mock |
| RAG_PARSE_MOCK | false | 解析走 mock |
| RAG_LLM_BACKEND | ollama | ollama / openai / mock |
| RAG_LLM_MOCK | false | LLM 走 mock |
| RAG_OLLAMA_BASE_URL | http://localhost:11434/v1 | Ollama 的 OpenAI 兼容端点 |
| RAG_OPENAI_BASE_URL | （空） | OpenAI 兼容端点 |
| RAG_OPENAI_API_KEY | （空） | API Key |
| RAG_LLM_MODEL | llama3.1:8b | 生成模型名 |
| RAG_RRF_K | 60 | RRF 融合常数 |
| RAG_RETRIEVE_TOP_K | 20 | RRF 融合前的每路候选数 |
| RAG_FAISS_TOP_K | 20 | FAISS 稠密路候选数 |
| RAG_FTS_TOP_K | 20 | FTS5 关键词路候选数 |
| RAG_RERANK_TOP_K | 5 | 重排后保留数 |
| RAG_TRUSTED_PROXY | false | true 时信任反向代理注入的 X-Rag-Tenant/User/Group 头解析身份（ACL 依赖；开启时必须由 nginx 等可信代理注入且 CORS 不含 X-Rag-*，见 §4.2） |
| RAG_PORT | 8000 | 后端监听端口 |

---

## 6. 可观测端点

| 端点 | 用途 |
|------|------|
| `GET /api/v1/health` | DB 连通性 + 各模型就绪状态；`status: ok/degraded` |
| `GET /api/v1/config/backends` | LLM / Embedding / Rerank 后端类型与就绪详情 |
| `GET /api/v1/metrics` | 进程内计数器 + 延迟直方图（JSON），可接入 Prometheus |
| 日志 | 容器 stdout 为 JSON 单行日志（含请求方法/路径/状态码/耗时） |

指标示例（部分）：
```json
{
  "counters": {
    "document_uploads_total": 12,
    "documents_indexed_total": 11,
    "documents_failed_total": 1,
    "queries_total": 47,
    "citations_returned_total": 133,
    "errors_total": 0
  },
  "histograms": {
    "retrieve_latency_ms": {"count": 47, "avg_ms": 18.4, "p95_ms": 41.2, "min_ms": 6.1, "max_ms": 88.0},
    "llm_latency_ms": {"count": 47, "avg_ms": 3102.7, "p95_ms": 6804.0, "min_ms": 1203.0, "max_ms": 9105.0}
  }
}
```

---

## 7. 评测运行

- Web：进入「评测」页 → 选择 profile（默认 `public_nist`）→ 点击「运行评测」。
- 公开评测（默认，真实公开 PDF + 自建 gold，18 题）：

```bash
bash scripts/evaluation/prepare.sh      # 下载+校验 NIST PDF（SHA-256）→ 构建语料 → 验证 gold（fail-closed）
bash scripts/evaluation/run.sh          # 确定性基线评测 → work/eval_reports/public_nist_report.json
./scripts/docker/manage.sh eval run     # 容器内运行（./work:/work 挂载，报告落宿主 work/）
```

- 旧内嵌 22 条手写问答为 `synthetic_smoke` profile：`cd backend && python -m app.evaluation.runner`，或评测页选择该 profile。
- `POST /api/v1/evaluation/run` 未 prepare 时返回 **409** 并提示先运行 `scripts/evaluation/prepare.sh`。
- 指标口径、CI 与 provenance 说明见 `docs/BENCHMARK_CARD.md`、`docs/EVALUATION_PROTOCOL.md`；真实模型适配器（Docling/bge-m3/reranker/LLM）当前全部 NOT_RUN，真实部署下切换 bge-m3（`EMBED_MOCK=false`）后需重新评测并更新 provenance。

---

## 8. 隔离验收栈（docrag-acceptance）

正式验收使用独立 Compose project（不触碰常规部署卷）：

| 项 | 值 |
|----|----|
| Compose 文件 | `docker-compose.acceptance.yml`（project 名 `docrag-acceptance`） |
| 入口 | `http://127.0.0.1:3302`（frontend 80 → 3302；backend 8000 仅容器网络内） |
| 卷 | `draccept_data`（SQLite+PDF）、`draccept_models`（模型权重）、`./work:/work`（评测缓存与报告） |
| 身份 | 默认 MOCK + `RAG_TRUSTED_PROXY=true`；nginx 注入 `X-Rag-Tenant "default"` / `X-Rag-User "demo"` |
| 管理 | `./scripts/docker/manage.sh {build|up|down|start|stop|restart|status|logs|eval}`（`down` 不带 `-v`，保留数据卷） |

```bash
./scripts/docker/manage.sh build && ./scripts/docker/manage.sh up
./scripts/docker/manage.sh status      # 等待 backend healthy（healthcheck 探测 /api/v1/health）
./scripts/docker/manage.sh eval run    # 容器内 public_nist 评测
./scripts/docker/manage.sh down        # 停栈（保留卷）
```

---

## 9. 故障排查

| 现象 | 可能原因 | 处理 |
|------|----------|------|
| 问答返回 503「模型未就绪」 | 真实后端未启用或权重未下载 | 确认 `*_MOCK=false` 且模型已就绪；或临时改回 MOCK |
| 解析失败「文件可能加密/损坏」 | 加密 PDF 或 Docling 不支持 | 用户提供非加密 PDF；检查 backend 日志 |
| 引用跳转不到页 | 该引用未携带 `bbox` | 前端降级为整页高亮；确认后端 chunk 透传 `bbox` |
| 前端白屏 | nginx 未反代 / 后端未起 | 确认 `docker compose` 两服务均 healthy，`/api/v1/health` 可访问 |
| 评测接口返回 409 | `public_nist` 未 prepare（无 `work/eval_corpus.json`）或语料与 manifest 版本不符 | 先运行 `scripts/evaluation/prepare.sh` 后重试；语料版本不符时删除 `work/eval_corpus.json` 重新 prepare |
| 问答返回 409「知识库为空」 | 当前身份无可见文档或显式空范围 | 上传文档或调整 ACL 后重试（见 MATURITY_MATRIX §3） |

---

## 10. 生产加固建议（非 MVP 必做，供参考）

- 前端 nginx 启用 HTTPS（反向代理前加 TLS 终止或前置 LB）。
- 多租户生产：在网关层接入 OIDC/企业 IdP，认证后注入 `X-Rag-*` 身份头（后端不内置认证；`RAG_TRUSTED_PROXY=true` 且仅允许经 nginx 访问后端）。
- 后端置于私有网络，仅经 nginx 暴露 `/api`；启用速率限制与输入校验（代码已含基础校验）。
- 模型权重预置进镜像或私有模型仓库，避免运行时外网拉取。
- 将 `/api/v1/metrics` 接入 Prometheus + Grafana；日志接入集中式采集。
- 大语料（>100 万 chunk）时 FAISS 由 IndexFlatIP 升级为 IVF/PQ（代码预留切换点）。
