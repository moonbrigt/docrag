# AGENTS.md — DocRAG 开发指引（WSL 原生）

可本地部署的文档 RAG Web 应用（React 前端 + FastAPI 后端）：PDF 上传 → Docling 解析（page_no+bbox 溯源）→ 结构化分块 → FAISS+FTS5 混合检索 → 重排 → 带页码引用回答 → PDF 高亮跳转。
**修改前必读**：本文档 + `docs/README.md`（唯一事实来源索引）。

## 运行环境（2026-08 迁移后现状）

- 唯一工作/运行环境：**WSL（Ubuntu，目录 `/home/z1050/Projects/docrag`）**，固定不移。
- 已弃用 Windows 与 Docker；一切命令、路径、文档以 Linux/WSL 为准。
- 后端 venv：`backend/.venv`（已建，Python 3.12）。
- 前端依赖：`frontend/node_modules`（已装）。
- Node 由 nvm 管理（v24）；非交互 shell 需先 `source ~/.nvm/nvm.sh`，否则 `node`/`npm` 不在 PATH。
- 模型后端默认 **mock（离线开箱即用，确定性、不下载权重）**；真实模型（bge-m3 / reranker / docling / LLM）需在设置页或 env 显式开启（`RAG_*_MOCK=false`）。
- 远端唯一事实来源：`https://github.com/moonbrigt/docrag.git`（分支 `main`）。
- Docker 遗留（`docker-compose*.yml`、`scripts/docker/`、各处 `Dockerfile`、`frontend/nginx.conf`）已删除，勿再作部署依据。

## 目录结构（开发时对照）

```
docrag/                        # 仓库根（WSL: /home/z1050/Projects/docrag）
├── AGENTS.md                  # 本文件：开发入口 + 环境现状
├── README.md                  # 项目总览 + 目录树 + 工程纪律
├── backend/                   # FastAPI 后端
│   ├── .venv/                 # Python 3.12 虚拟环境（已建）
│   ├── app/                   # 业务代码
│   │   ├── main.py            # 入口（FastAPI 装配，/api/v1 前缀）
│   │   ├── config.py          # 配置（RAG_ 前缀，pydantic-settings）
│   │   ├── auth.py            # 身份解析（trusted-proxy 头 → Principal）
│   │   ├── db.py              # SQLite 连接 + 串行化写（FTS / 向量 BLOB）
│   │   ├── routes/            # 薄路由（documents/search/chat/eval/meta/trace/config）
│   │   ├── services/          # 业务：document/pipeline/retrieve/generate/citation/trace
│   │   ├── repositories/      # 数据访问：chunk/document/trace
│   │   ├── core/              # 基础设施：embeddings/reranker/llm/parser/faiss_store/runtime_config/metrics
│   │   ├── evaluation/        # 评测 runner + public_dataset + 指标
│   │   ├── tests/             # smoke + 公开评测测试
│   │   └── schemas.py         # Pydantic 模型
│   └── requirements*.txt      # 运行时/dev/eval/ml 依赖
├── frontend/                  # React SPA
│   └── src/
│       ├── components/        # common/layout/ui（CitationChip/AppShell/Button 等）
│       ├── pages/             # Chat / Documents / Evaluation / Settings
│       ├── api/ lib/ hooks/   # 请求封装 / 工具 / 状态
│       ├── design/            # DESIGN.md + design-tokens.json（颜色唯一来源）
│       ├── styles/            # globals.css / tokens.css
│       └── types/             # 与后端契约对齐的 TS 类型
├── docs/                      # SPEC.md / architecture.md / ENGINEERING.md / DEPLOYMENT.md
│                              # + 成熟度六卡（MATURITY_MATRIX / DATA_CARD / BENCHMARK_CARD
│                              #   / EVALUATION_PROTOCOL / REPRODUCE / VALIDATION）
├── scripts/                   # evaluation/*（评测脚本）
└── work/                      # 评测工作区（被 gitignore，PDF 缓存与报告产物）
```

## 文档路由（改代码前按序查阅）

| 文档 | 用途 | 权威性 |
|---|---|---|
| `docs/README.md` | **唯一事实来源**：速查表、API 清单（22 端点）、裁决记录、维护规则 | ★★★ 冲突时以「源码 + 本文档」为准 |
| `docs/SPEC.md` | 需求契约：MVP 范围、API/DB/页面/Token、EARS 验收标准 | ★★ 锁定期内禁止改范围；变更走 §13 |
| `docs/architecture.md` | 分层图、数据流、混合检索、部署拓扑 | ★★ 架构事实 |
| `docs/DEPLOYMENT.md` | 部署、env 一览、真实模型切换、故障排查 | ★★ 部署事实 |
| `docs/ENGINEERING.md` | 关键决策、技术权衡、验证状态与已知边界 | ★ 工程说明 |
| `frontend/src/design/` | 设计系统权威版：DESIGN.md / design-tokens.json / component-states.md / wireframes.md | ★★ token 以 design-tokens.json 为源 |

## 修 bug 标准流程

1. 读 `docs/README.md` §2 速查表与 `docs/SPEC.md` 对应章节；先跑后端 `pytest -q` 看现有红测试
2. 复现：后端 `backend/.venv/bin/uvicorn app.main:app`（MOCK 全开）；前端 `npm run dev`
3. 修复时保持分层：`routes`（薄路由）→ `services`（业务）→ `repositories`（数据访问）→ `core`（基础设施）；前端 `components/pages/api/lib/hooks` 分离；单文件 ≤300 行
4. 加/改测试（`backend/app/tests/`），`pytest -q` 全绿；前端改动需 `npm run build`（tsc --noEmit）通过
5. **同步文档**：改 API/env/DB/指标/状态机/token 后，在 `docs/README.md` §2 更新并在 §5 追加裁决记录；SPEC 契约变更走 §13

## P0 红线（勿违反）

- 禁止 emoji 功能图标（全项目唯一图标源：Lucide `lucide-react`）
- 颜色单一来源 `frontend/src/design/design-tokens.json`（accent `#3E63DD` / citation `#F5B544`），组件零硬编码 hex
- 禁止紫粉渐变；禁止 AI 模板味文案
- LLM key 只走 env / `.env`（`RAG_` 前缀，见 `backend/app/config.py`）
- 混合检索 + 重排默认开启，禁止静默降级为 BM25
- `chunks.page_no` 必填（F6 溯源硬约束）；写库走 `db.write` 串行化（防 SQLite 并发损坏）
- 评测复用运行时单例服务（embedding/reranking），CLI 入口显式加载运行时配置覆盖，保证与设置页一致
- 模型配置（embedding/reranking/parsing）由前端设置页选择，不硬编码；`mock` 选中时模型名输入禁用并显示「— Mock 下不适用 —」

## 已知薄弱点（修 bug 优先清单）

- 真实模型链路：Docling 真实解析、bge-m3 嵌入、真实 LLM 均已在 WSL 实测通过；bge-reranker-v2-m3 真实 CrossEncoder 已在 2026-08-21 真实模型消融评测中加载并验证（MRR 0.752→0.906，见 BENCHMARK_CARD §12）——但生产 runtime_config 当前仍配置为 mock 重排（CPU 下 wall ×4.7 的延迟代价），词法 vs 神经重排同口径对比是遗留验证项
- 前端无自动化测试（可补 vitest + testing-library，优先覆盖 CitationChip 引用跳转与 SSE 解析）
- 后端测试只覆盖 smoke（health/documents）与评测；`chat` SSE 流、删除同步、双后端切换无专门测试
- 评测指标已闭环：mock 基线 MRR 0.7469；真实全链路（bge-m3 + bge-reranker + 真实 LLM）recall@5 0.9375 / MRR 0.9062 / answer EM 0.333（BENCHMARK_CARD §12）
- 单 SQLite 连接 + asyncio.Lock 串行化写（高并发写入场景已知限制，见 backend/README §8）

## 常用命令（均在 WSL 执行）

```bash
cd /home/z1050/Projects/docrag

# 后端（backend/ 下）
cd backend
./.venv/bin/python -m pytest -q                    # 全量测试
./.venv/bin/python -m uvicorn app.main:app --port 8000   # 启动；模型后端以 runtime_config(设置页) 为准
./start_mock.sh                                    # 一键离线 MOCK 启动（已把 runtime_config 置为 mock）
./.venv/bin/python -m app.evaluation.runner        # 旧 22 条手写评测
./.venv/bin/python -m app.evaluation.real_full_runner --variants hybrid_rerank_llm   # 真实模型消融（需本地权重+LLM 配置，约 20 分钟/变体）

# 前端（frontend/ 下）
cd ../frontend
source ~/.nvm/nvm.sh   # WSL 下 node/npm 需先加载 nvm
npm run dev      # http://localhost:5173（/api 代理到 :8000）
npm run build    # tsc --noEmit && vite build
```