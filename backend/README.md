# DocRAG 后端（FastAPI）

文档 RAG 应用的后端全链路：上传 → Docling 解析 → 结构化分块 → bge-m3 混合嵌入 →
FAISS + FTS5 混合检索 → bge-reranker 精排 → 双后端 LLM 带页码引用的流式问答，
以及内置评测集。技术栈与接口严格遵循 `docs/SPEC.md`。

## 1. 目录结构

```
backend/
├── requirements.txt          # 轻量运行时依赖（离线 MOCK 可跑；真实模型见 requirements-ml.txt）
├── requirements-dev.txt      # 测试/质量依赖（pytest/httpx/ruff）
├── requirements-ml.txt       # 真实模型依赖（docling / flag-embedding / sentence-transformers 等）
├── .env.example              # 环境变量示例（复制为 .env 后修改）
├── app/
│   ├── main.py               # 入口：仅装配路由 + CORS + 启动重建 FAISS（零业务逻辑）
│   ├── config.py             # pydantic-settings，RAG_ 前缀注入
│   ├── db.py                 # SQLite 单连接 + asyncio.Lock + 建表（WAL）
│   ├── schemas.py            # 请求/响应 pydantic 模型
│   ├── core/                 # 基础设施（与框架解耦）
│   │   ├── embeddings.py      # bge-m3(稠密+sparse) + 确定性 mock
│   │   ├── reranker.py        # bge-reranker-v2-m3 + mock
│   │   ├── llm.py             # openai SDK 双后端(ollama/openai) + mock 流式
│   │   ├── faiss_store.py     # IndexFlatIP（归一化=cosine）+ numpy 兜底
│   │   ├── parser.py          # Docling(DocumentConverter+HybridChunker) + mock
│   │   └── errors.py          # 领域异常（映射 503/422）
│   ├── services/             # 业务逻辑（依赖只向下：routes→services→repositories）
│   │   ├── index_service.py   # 嵌入 + 持久化 + FAISS 增量/重建
│   │   ├── retrieve_service.py# 混合检索 + RRF(k=60) 融合
│   │   ├── rerank_service.py  # 精排 top-20→top-5
│   │   ├── citation_service.py# 解析 [n] 引用 → 页码/bbox
│   │   ├── generate_service.py# 组装 prompt + SSE 流式生成
│   │   ├── document_service.py# 列表/详情/删除/原文文件定位
│   │   └── pipeline_service.py# 上传后异步流水线（状态机）
│   ├── repositories/         # 数据访问（documents / chunks + FTS5）
│   ├── routes/               # 薄路由（校验 + 调服务 + 组装响应）
│   │   ├── documents.py  search.py  chat.py  meta.py  evaluation.py
│   ├── evaluation/           # dataset.json(≥20 条中英问答) + runner.py
│   └── tests/                # pytest 冒烟（conftest 开启全 mock）
└── data/                     # 上传 PDF 原文 + 运行时产物（gitignore）
```

## 2. 启动

```bash
cd backend
python -m pip install -r requirements.txt      # 不含模型权重，仅依赖
cp .env.example .env                            # 按需修改

# 开发
uvicorn app.main:app --reload --port 8000

# 生产（多 worker）
gunicorn app.main:app -k uvicorn.workers.UvicornWorker -w 2 -b 0.0.0.0:8000
```

接口统一前缀 `/api/v1`，文档见 `/docs`。

## 3. 环境变量（RAG_ 前缀）

| 变量 | 默认 | 说明 |
|------|------|------|
| RAG_DB_PATH | ./app.db | SQLite 路径 |
| RAG_DATA_DIR | ./data | 上传 PDF 原文与运行时目录 |
| RAG_MODEL_DIR | ./models | 模型权重挂载目录 |
| RAG_EMBED_BACKEND / RAG_EMBED_MOCK | bge-m3 / false | 嵌入后端；true 走确定性 mock |
| RAG_RERANK_BACKEND / RAG_RERANK_MOCK | bge-reranker-v2-m3 / false | 重排后端；true 走 mock |
| RAG_PARSE_BACKEND / RAG_PARSE_MOCK | docling / false | 解析后端；true 走 mock |
| RAG_LLM_BACKEND | ollama | ollama / openai / mock |
| RAG_OLLAMA_BASE_URL | http://localhost:11434/v1 | Ollama OpenAI 兼容端点 |
| RAG_OPENAI_BASE_URL / RAG_OPENAI_API_KEY | "" | OpenAI 兼容端点 |
| RAG_LLM_MODEL | llama3.1:8b | 生成模型名 |
| RAG_RRF_K / RAG_RETRIEVE_TOP_K / RAG_RERANK_TOP_K | 60 / 20 / 5 | 检索参数 |
| RAG_CORS_ORIGINS | localhost:5173 等 | 逗号分隔的额外前端源 |

双后端 LLM 通过 `base_url` 切换（同一 openai SDK），零分支。

## 4. 降级与就绪语义（重要）

重模型（bge-m3 ≈2.2GB / reranker 568MB）**运行时挂载 volume 或首次自动拉取，镜像保持精简**。
后端就绪状态由 `GET /api/v1/config/backends` 与 `GET /api/v1/health` 暴露：

- 显式开启 `RAG_*_MOCK=true` → 走确定性 mock，状态 `ready`，可完全离线验证全链路。
- 未开启 mock 且真实模型不可用（权重缺失/未安装）→ 该后端 `ready=false`，
  需要它的接口返回 **503 + 明确中文文案**（如「嵌入模型未就绪…」），**绝不静默替换模型、绝不强行下载**。
- PDF 解析失败（加密/损坏）或流水线异常 → 文档状态置 `failed` 并记录明确错误。

最小运行配置（仅验证后端骨架，不动大模型）：

```bash
RAG_EMBED_MOCK=true RAG_RERANK_MOCK=true RAG_PARSE_MOCK=true RAG_LLM_MOCK=true \
uvicorn app.main:app --port 8000
```

真实部署建议 ≥8GB RAM、≥10GB 空闲磁盘（Spec §4）。

## 5. 关键接口

| Method | Path | 说明 |
|--------|------|------|
| POST | /api/v1/documents | 上传 PDF，触发 解析→分块→嵌入→索引 后台流水线（202 + document_id） |
| GET | /api/v1/documents | 文档列表（含状态/页数/分块数） |
| GET | /api/v1/documents/{id} | 详情 + 分块预览（每块含 page_no / bbox / section） |
| DELETE | /api/v1/documents/{id} | 删除并同步清理向量 BLOB 与 FTS 条目（204） |
| GET | /api/v1/documents/{id}/file | 返回完整原始 PDF 文件流（原上传文件名），前端 pdfjs 加载并按归一化 bbox 高亮 |
| POST | /api/v1/search | 混合检索 + 重排，返回候选与分数 |
| POST | /api/v1/chat | 流式问答（SSE：delta / citation / done / error），强制 [页码] 引用 |
| GET | /api/v1/config/backends | 双后端就绪状态 |
| GET | /api/v1/health | 健康检查 |
| GET | /api/v1/metrics | 可观测指标（计数器 + 延迟直方图，JSON） |
| POST | /api/v1/evaluation/run | 运行内置评测集，输出引用准确率/召回@K/MRR |

## 6. 评测

`app/evaluation/dataset.json` 内嵌 2 篇文档 / 12 页语料 + 22 条中英混合问答（标准出处为页码）。
`runner.py` 用确定性 mock 嵌入离线构建索引并计算：

- Citation Accuracy（页码命中率）
- Recall@K（K=5/10）
- Hit Rate@K
- MRR

```bash
# 通过接口
curl -X POST http://localhost:8000/api/v1/evaluation/run

# 或直接运行
python -m app.evaluation.runner
```

## 7. 测试

```bash
python -m pip install pytest httpx
pytest -q                 # conftest 默认开启全 mock，覆盖 health/documents/search/chat/eval
```

## 8. 已知限制

- 本仓库**不含模型权重**：bge-m3 / reranker 需运行时拉取或挂载；离线仅 mock 可用。
- Docling 解析真实 PDF 首次会下载布局模型；mock 模式不依赖它。
- FAISS 索引常驻内存，启动时从 SQLite 重建；删除文档后整体重建以保证一致（MVP 可接受）。
- 单 SQLite 连接 + asyncio.Lock 串行化写，满足零外部依赖；高并发写入场景建议后续换 aiosqlite/Postgres。
- 前端样式/emoji 由前端负责；本后端返回文案不含 emoji、不引入紫粉配色字段。
