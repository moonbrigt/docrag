# 贡献指南

DocRAG 是独立开源项目，欢迎以 issue 形式提问与反馈；代码贡献请先阅读 [AGENTS.md](AGENTS.md)（开发指引与 P0 红线）与 [docs/README.md](docs/README.md)（唯一事实来源索引）。

## 环境

- Python 3.12（后端，venv `backend/.venv`），Node（前端，经 nvm 管理 v24）；限 WSL（Ubuntu）环境。
- 离线演示无需任何模型权重：默认 `RAG_*_MOCK=true`；真实模型需在设置页或 env 显式开启。

## 本地开发

```bash
# 后端（backend/ 下）
source ~/.nvm/nvm.sh   # WSL 下需先加载 nvm（若需 node/npm）
./.venv/bin/python -m uvicorn app.main:app --reload --port 8000   # MOCK 用 ./start_mock.sh

# 前端（frontend/ 下）
npm install && npm run dev   # http://localhost:5173
```

## 提交前门禁（必须全绿）

```bash
cd backend && ./.venv/bin/python -m pytest -q   # 全量测试（当前 79 项）
./.venv/bin/python -m compileall -q app         # 语法检查
cd ../frontend && npm run build                 # tsc --noEmit + vite build
```

- 分层纪律：`routes`（薄路由）→ `services`（业务）→ `repositories`（数据访问）→ `core`（基础设施）；依赖只向下，单文件 ≤300 行。
- 改动 API / env / DB / 指标 / 状态机 / token 后，同步更新 `docs/README.md` §2 速查与 §5 裁决记录；SPEC 契约变更走 §13。
- P0 红线：禁 emoji 功能图标（唯一图标源 lucide-react）；颜色单一来源 `frontend/src/design/design-tokens.json`；混合检索 + 重排默认开启，禁止静默降级；`chunks.page_no` 必填。

## 评测（改语料/指标前必读）

- 数据集与指标口径见 `docs/DATA_CARD.md` / `docs/BENCHMARK_CARD.md`；增删题目会改变 hard-negative 组指标，跨报告对比需固定 manifest 版本。
- gold 绝不进入检索/生成管线；真实模型与 mock 的验证状态分开标注（VERIFIED / NOT_RUN）。

## 提交信息风格

小写前缀 + 动词短语：`feat:` `fix:` `docs:` `test:` `refactor:`，如 `feat: add runtime model api settings`。
