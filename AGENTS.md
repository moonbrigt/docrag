# AGENTS.md — DocRAG 开发指引（Codex / 开发者入口）

可私有部署的文档 RAG Web 应用（React 前端 + FastAPI 后端）：PDF 上传 → Docling 解析（page_no+bbox 溯源）→ 结构化分块 → FAISS+FTS5 混合检索 → 重排 → 带页码引用回答 → PDF 高亮跳转。
**修改前必读**：本文档 + `docs/README.md`（唯一事实来源索引）。

## 项目速览

- 后端：`backend/`（FastAPI，入口 `app/main.py`，API 前缀 `/api/v1`）
- 前端：`frontend/`（React 19 + Vite 8 + TS 5.6 + Tailwind 4 + Radix + Lucide + pdfjs）
- 测试：后端 `python -m pytest -q`（61 个测试项，含 ACL/生命周期/版本/chat 与公开评测测试）；前端无测试
- 部署：`docker compose up --build` → http://localhost:3002（默认 MOCK 离线；3000 常被本机其他服务占用）
- 评测：`cd backend && python -m app.evaluation.public_runner run`（NIST 公开评测，先 `scripts/evaluation/prepare.sh`；旧 22 条手写集为 `synthetic_smoke`，走 `python -m app.evaluation.runner`）
- 关键契约：`docs/SPEC.md`（12 章，Spec as Contract）

## 文档路由（改代码前按序查阅）

| 文档 | 用途 | 权威性 |
|---|---|---|
| `docs/README.md` | **唯一事实来源**：速查表、API 清单（11 端点）、10 条裁决记录、维护规则 | ★★★ 冲突时以「源码 + 本文档」为准 |
| `docs/SPEC.md` | 需求契约：MVP 范围、API/DB/页面/Token、EARS 验收标准 | ★★ 锁定期内禁止改范围；变更走 §13 |
| `docs/architecture.md` | 分层图、数据流、混合检索、部署拓扑 | ★★ 架构事实 |
| `docs/DEPLOYMENT.md` | 部署、env 一览、真实模型切换、故障排查 | ★★ 部署事实 |
| `docs/ENGINEERING.md` | 关键决策、技术权衡、验证状态与已知边界 | ★ 工程说明 |
| `../../PRD-文档RAG应用.md` | 产品需求（F1–F10） | ★ 背景 |
| `frontend/src/design/` | 设计系统权威版（顶层 `web/` 已 Superseded）：DESIGN.md / design-tokens.json / component-states.md / wireframes.md | ★★ token 以 design-tokens.json 为源 |

## 修 bug 标准流程

1. 读 `docs/README.md` §2 速查表与 `docs/SPEC.md` 对应章节；先跑后端 `pytest -q` 看现有红测试
2. 复现：后端 `.venv` 起 `uvicorn app.main:app`（MOCK 全开）；前端 `npm run dev`
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

## 已知薄弱点（修 bug 优先清单）

- 真实模型链路：Docling 真实解析已在 acceptance 镜像档容器内 **VERIFIED**（48 页真实摄取，见 `docs/VALIDATION.md` §4）；bge-m3 / bge-reranker-v2-m3 / LLM 仍未实测（`requirements-ml.txt` 安装路径、权重加载、`EMBED_MOCK=false` 场景；真实 LLM 需密钥/成本授权）
- 前端无自动化测试（可补 vitest + testing-library，优先覆盖 CitationChip 引用跳转与 SSE 解析）
- 后端测试只覆盖 smoke（health/documents）与评测；`chat` SSE 流、删除同步、双后端切换无专门测试
- 评测 MRR 0.52（Mock 下）偏低——真实模型下需复核；Recall/HitRate 已 1.0
- 容器内 Swagger 不可访问（nginx 仅反代 `/api/`，`/docs` 未代理；本地开发走 `:8000/docs`）
- 单 SQLite 连接 + asyncio.Lock 串行化写（高并发写入场景已知限制，见 backend/README §8）

## 常用命令

```bash
# 后端（backend/ 下，.venv 已建）
./.venv/Scripts/python.exe -m pytest -q
./.venv/Scripts/python.exe -m uvicorn app.main:app --port 8000        # MOCK 需设 RAG_*_MOCK=true
./.venv/Scripts/python.exe -m app.evaluation.runner                   # 评测 22 条

# 前端（frontend/ 下）
npm run dev       # http://localhost:5173
npm run build     # tsc --noEmit && vite build

# 容器
docker compose up --build   # http://localhost:3002（默认 MOCK 离线）
```
