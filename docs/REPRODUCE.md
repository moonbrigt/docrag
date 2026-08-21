# DocRAG 复现指南（Reproduce）

> 本指南只描述「复现公开评测（public_nist）」与相关验证的最小路径；完整部署与部署详情见 `docs/DEPLOYMENT.md`、`docs/EVALUATION_PROTOCOL.md`。

## 1. 环境要求

| 项 | 要求 | 本次验证实测 |
|----|------|--------------|
| Python | 3.12 | Python 3.12（backend venv） |
| Node | 通过 nvm 管理（v24） | node v24（`npm run build` 通过） |
| 依赖 | 后端 `requirements.txt` + `requirements-dev.txt`（测试）+ `requirements-eval.txt`（pypdf 等评测依赖） | 评测 venv 含 fastapi 0.115.13 / pypdf 6.15.0 / faiss-cpu 1.14.3 / pytest / numpy |
| 网络 | MOCK 全离线；`prepare` 首次需联网下载两份 NIST PDF（DOI） | 已缓存于 `work/source_cache/`（SHA-256 校验通过） |

> 依赖拆分：`requirements.txt`（轻量运行时）、`requirements-dev.txt`（pytest/httpx/ruff）、`requirements-eval.txt`（评测：pypdf 等）、`requirements-ml.txt`（真实模型重依赖）。

## 2. 本地路径（开发/调试，WSL 原生）

```bash
# 0) 准备环境
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt -r requirements-eval.txt

# 1) 下载并校验 PDF（fail-closed：尺寸 + SHA-256）
bash ../scripts/evaluation/download.sh   # 默认工作目录 <repo>/work

# 2) 构建语料 + 验证全部 gold（prepare）
bash ../scripts/evaluation/prepare.sh

# 3) 运行确定性评测（报告原子写入）
bash ../scripts/evaluation/run.sh

# 4) 复验语料与报告
./.venv/bin/python -m app.evaluation.public_runner --work-dir ../work verify

# 5) 测试
./.venv/bin/python -m pytest -q          # 全量（107 passed）
./.venv/bin/python -m pytest -q app/tests/test_public_evaluation.py   # 评测专项

# 前端（另开终端）
cd frontend && source ~/.nvm/nvm.sh && npm install && npm run build   # tsc --noEmit + vite build
npm run lint                             # eslint（本次实测零告警）
```

产物：

| 产物 | 路径 |
|------|------|
| PDF 缓存 | `work/source_cache/{NIST.AI.100-1,NIST.AI.600-1}.pdf` |
| 语料 | `work/eval_corpus.json`（JSONL，103 chunk） |
| 评测报告 | `work/eval_reports/public_nist_report.json` |

## 2.1 真实模型消融复现（可选，需权重与 LLM 配置）

```bash
# 前置：requirements-ml.txt 已装；设置页/runtime_config 已配好可用 LLM；HF 权重已缓存（bge-m3 + bge-reranker-v2-m3）
./.venv/bin/python -m app.evaluation.real_full_runner                     # 四变体全跑（约 30 分钟，CPU）
./.venv/bin/python -m app.evaluation.real_full_runner --variants hybrid_rerank_llm --out real_full_rerank.json
./.venv/bin/python -m app.evaluation.real_full_runner --variants bm25_real_llm hybrid_lexical_llm --out real_full_lexical.json
```

产物 `work/real_full_report.json`（含 `real_full_{bm25,hybrid,rerank,lexical}.json` 单变体/分组复跑）。检索类指标确定性可复现；answer 类指标受 LLM 采样影响（±0.07 内波动）。预期值与边界见 `docs/BENCHMARK_CARD.md` §12。

## 3. 预期输出（expected outputs，2026-08-12 复跑核对）

复现 `run` 后，报告 `work/eval_reports/public_nist_report.json` 的关键字段应与下表一致（除 `created_at` 与 `corpus.source_cache` 路径外，**字节级一致**——2026-08-12 在独立工作目录复跑验证）：

| 字段 | 预期值 |
|------|--------|
| profile | `public_nist` |
| manifest.id / version | `nist_ai_rmf_public_v1` / `1.0.0` |
| corpus.n_chunks / n_chars / pages_excluded | 103 / 258451 / 9 |
| baseline.name / keys | `bm25 + lexical-rerank + extractive-answer` / `none` |
| metrics.recall@1 / recall@5 | 0.625 / 0.84375 |
| metrics.mrr / ndcg@5 | 0.746875 / 0.7538503944778031 |
| metrics.citation_recall | 0.84375 |
| metrics.answer_em / answer_f1 | 0.0625 / 0.0703125 |
| metrics.eligible / total | 16 / 18 |
| metrics.unanswerable_correct | 0.0 |
| determinism.verified | true |
| provenance.* | 全部 `NOT_RUN` |

完整指标表、CI 与切片见 `docs/BENCHMARK_CARD.md` §3/§5。

## 5. 已知边界（复现时须知）

- 全量 `pytest` 已恢复全绿：79 passed（2026-08-20 复核；期间发现并修复了 `backend/app/db.py` 全新库迁移顺序回归，双路径回归验证通过，详见 `docs/VALIDATION.md` §3.1/§5）。
- `prepare` 需要外网访问 DOI 重定向；已缓存文件仅做 SHA-256 校验，不重复下载。
- 评测是每页一个 chunk 的粗粒度语料（103 chunk），与产品管线（Docling HybridChunker 分块）口径不同，两者指标不可直接对比。
