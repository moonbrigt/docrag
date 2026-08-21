# DocRAG

<div align="center">

**可本地部署的文档溯源问答系统**

PDF 上传 → Docling 结构化解析 → 混合检索 → 引用门控生成 → PDF 高亮跳转

![CI](https://github.com/moonbrigt/docrag/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/License-MIT-blue)
![Python](https://img.shields.io/badge/Python-3.12-3776AB)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![React](https://img.shields.io/badge/React-19-61DAFB)

</div>

---

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔍 **混合检索** | FAISS 稠密向量 + SQLite FTS5 关键词双路召回，RRF(k=60) 融合，bge-reranker 精排 |
| 📄 **像素级溯源** | Docling HybridChunker 保留 page_no + bbox 坐标，点击引用跳页高亮 |
| 🧪 **评测工程化** | NIST 公开 PDF 18 题 gold 标注，bootstrap/Wilson 95% CI，四路消融对比 |
| 🔐 **多租户 ACL** | Principal(tenant/user/groups) + fail-closed 可见性，可信反向代理注入 |
| 📊 **可观测性** | 结构化 JSON 日志 + /metrics 计数器与延迟直方图(p50/p95/max) |
| ⚡ **离线可跑** | 默认 MOCK 模式零外部依赖，一条命令起全套；真实模型设置页运行时切换 |

## 🏗️ 架构

```
浏览器 (React SPA)
   │  /api/v1
   ▼
FastAPI 网关 (:8000)
   ├─ 上传 → Docling 解析(page_no+bbox) → 结构化分块 → FAISS+FTS5 索引
   ├─ 提问 → 混合检索(RRF) → Rerank → LLM SSE 生成(引用缓冲门控)
   └─ 可观测性: 结构化日志 + /metrics
存储: SQLite(元数据+FTS5+向量BLOB) + FAISS(内存索引)
```

## 🚀 快速开始

### 一键启动

```bash
git clone https://github.com/moonbrigt/docrag.git
cd docrag

# 后端
cd backend && ./start_mock.sh

# 前端（另开终端）
cd frontend && npm run dev   # http://localhost:5173
```

默认 **MOCK 模式**，离线可跑全链路。真实模型在设置页配置即可。

### 接入真实模型

打开 `http://localhost:5173/settings`：

| 模块 | 支持后端 |
|------|---------|
| LLM | Ollama / OpenAI 兼容 API（硅基流动、OpenRouter 等） |
| 嵌入 | bge-m3（本地）/ OpenAI 兼容 /v1/embeddings |
| 重排 | bge-reranker-v2-m3 / mock |
| 解析 | Docling（结构化）/ pypdf（轻量）/ mock |

### 运行评测

```bash
cd backend
bash ../scripts/evaluation/prepare.sh   # 下载 NIST PDF + 构建语料
bash ../scripts/evaluation/run.sh       # 运行评测，报告写入 work/
```

## 📊 评测结果

**NIST AI 100-1 / 600-1（18 题，16 answerable + 2 unanswerable）**

| 指标 | recall@1 | recall@5 | MRR | nDCG@5 | 引用召回 | 答案 EM |
|------|---------|---------|-----|--------|---------|--------|
| mock 基线 | 0.625 | 0.844 | 0.747 | 0.754 | 0.844 | 0.063 |
| 真实模型 | 0.813 | 0.938 | 0.906 | 0.907 | 0.813 | 0.214 |

**检索消融对比（四路变体）**

| 变体 | recall@5 | MRR | nDCG@5 |
|------|---------|-----|--------|
| BM25 + 词法重排 | **0.844** | **0.747** | **0.754** |
| mock 稠密 | 0.594 | 0.440 | 0.469 |
| RRF 混合 | 0.750 | 0.641 | 0.663 |
| 混合 + 词法重排 | 0.750 | 0.703 | 0.709 |

> 详细指标、CI、切片分析见 [docs/BENCHMARK_CARD.md](docs/BENCHMARK_CARD.md)

## 🖼️ 界面预览

![端到端演示](docs/screenshots/demo.gif)

| 概览 | 文档库 | 问答 | 评测 | 设置 |
|------|--------|------|------|------|
| ![概览](docs/screenshots/home.png) | ![文档库](docs/screenshots/documents.png) | ![问答](docs/screenshots/chat.png) | ![评测](docs/screenshots/evaluation.png) | ![设置](docs/screenshots/settings.png) |

## 🛠️ 技术栈

**前端**：React + TypeScript + Vite + Tailwind CSS + pdfjs-dist

**后端**：FastAPI + SQLite（FTS5）+ FAISS + Docling + bge-m3 + bge-reranker + OpenAI 兼容 API

**评测**：NIST 公开 PDF 评测集 + LLM-as-Judge + bootstrap/Wilson CI

## 📁 项目结构

```
docrag/
├── backend/
│   ├── app/
│   │   ├── core/            # parser / embeddings / reranker / llm / faiss_store / metrics
│   │   ├── services/        # pipeline / retrieve / rerank / generate / citation
│   │   ├── repositories/    # document / chunk / trace (SQLite + FTS5)
│   │   ├── routes/          # 22 个 RESTful 端点 (/api/v1)
│   │   ├── evaluation/      # 评测 runner + 指标 + 消融
│   │   └── tests/           # 107 项自动化测试
│   └── start_mock.sh        # 一键离线启动
├── frontend/
│   └── src/
│       ├── pages/           # Home / Documents / Chat / Evaluation / Settings
│       ├── components/      # CitationChip / PDFPreview / ScopePanel
│       └── design/          # Design Token 系统（双主题）
├── docs/                    # SPEC / architecture / BENCHMARK_CARD / ...
└── scripts/evaluation/      # 评测门禁脚本
```

## ⚙️ 配置

所有配置通过 `RAG_` 前缀环境变量注入，支持设置页运行时覆盖：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `RAG_LLM_MOCK` | true | LLM 走 mock（离线） |
| `RAG_EMBED_MOCK` | true | 嵌入走 mock |
| `RAG_RERANK_MOCK` | true | 重排走 mock |
| `RAG_PARSE_MOCK` | true | 解析走 mock |
| `RAG_CACHE_TTL` | 300 | 查询缓存 TTL（秒），0=禁用 |
| `RAG_TRUSTED_PROXY` | false | 信任反向代理注入的身份头 |

完整配置见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## 📖 API

22 个端点，统一前缀 `/api/v1`：

| 端点 | 说明 |
|------|------|
| `POST /documents` | 上传 PDF，触发异步索引 |
| `POST /chat` | SSE 流式问答（stage/delta/citation/no_answer/done） |
| `POST /search` | 检索调试 |
| `GET /metrics` | 可观测指标（计数器 + 延迟直方图） |
| `POST /evaluation/run` | 运行评测集 |
| `GET/PUT /config/settings` | 运行时模型配置 |

完整 API 文档见 [docs/SPEC.md](docs/SPEC.md)

## 🧪 测试

```bash
cd backend
./.venv/bin/python -m pytest -q   # 107 项全绿
```

覆盖：冒烟测试 + 成熟度（ACL/生命周期/SSE 契约/缓存/citation）+ 评测

## 🤝 贡献

欢迎贡献！请先阅读 [CONTRIBUTING.md](CONTRIBUTING.md)

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/amazing-feature`)
3. 提交更改 (`git commit -m 'feat: add amazing feature'`)
4. 推送到分支 (`git push origin feature/amazing-feature`)
5. 创建 Pull Request

## 📄 License

[MIT](LICENSE)

## 🙏 致谢

- [Docling](https://github.com/DS4SD/docling) — 文档解析与结构化分块
- [FAISS](https://github.com/facebookresearch/faiss) — 向量检索
- [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) — bge-m3 / bge-reranker
- [privateGPT](https://github.com/zylon-ai/privategpt) / [RAGFlow](https://github.com/infiniflow/ragflow) — 架构参考
