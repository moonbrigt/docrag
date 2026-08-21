# DocRAG

<div align="center">

**可本地部署的文档溯源问答系统**

PDF 上传 → Docling 结构化解析 → 混合检索 → 引用门控生成 → PDF 高亮跳转

![CI](https://github.com/moonbrigt/docrag/actions/workflows/ci.yml/badge.svg)
![License](https://img.shields.io/badge/License-MIT-blue)

</div>

---

## ✨ 特性

- **混合检索** — FAISS 稠密向量 + FTS5 关键词双路召回 + RRF 融合 + 可插拔重排
- **像素级溯源** — 引用携带页码 + bbox 坐标，点击跳页高亮
- **评测工程化** — NIST 公开 PDF 评测集，LLM-as-Judge 质量评分，CI 门禁
- **多租户 ACL** — 租户/用户/组级别可见性控制
- **离线可跑** — 默认 MOCK 模式零依赖，真实模型设置页切换

## 🏗️ 架构

```
浏览器 (React SPA)
   │
   ▼
FastAPI 后端
   ├─ 上传 → 解析 → 分块 → 向量索引
   ├─ 提问 → 混合检索 → 重排 → LLM 生成 → 引用校验
   └─ 可观测性（日志 + 指标）
存储: SQLite + FAISS
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

默认 **MOCK 模式**，离线可跑全链路。真实模型在设置页切换，无需改代码。

> 评测方法与指标见 [docs/BENCHMARK_CARD.md](docs/BENCHMARK_CARD.md)

## 🖼️ 界面预览

![端到端演示](docs/screenshots/demo.gif)

| 概览 | 文档库 | 问答 | 评测 | 设置 |
|------|--------|------|------|------|
| ![概览](docs/screenshots/home.png) | ![文档库](docs/screenshots/documents.png) | ![问答](docs/screenshots/chat.png) | ![评测](docs/screenshots/evaluation.png) | ![设置](docs/screenshots/settings.png) |

## 🛠️ 技术栈

React + FastAPI + FAISS + SQLite + Docling + bge-m3 + OpenAI SDK

## 📁 项目结构

```
docrag/
├── backend/    # FastAPI 后端
├── frontend/   # React SPA
├── docs/       # 规格文档
└── scripts/    # 评测脚本
```

## ⚙️ 配置

环境变量 + 设置页运行时覆盖，详见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## 📖 API

统一前缀 `/api/v1`，22 个端点。核心：`POST /documents`（上传）、`POST /chat`（SSE 问答）、`GET /metrics`（可观测）。完整文档见 [docs/SPEC.md](docs/SPEC.md)

## 🧪 测试

```bash
cd backend && python -m pytest -q
```

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
