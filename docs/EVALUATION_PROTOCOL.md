# DocRAG 评测协议（Evaluation Protocol）

> 本次文档更新，数据核对日期 2026-08-12。协议与实现核对一致：`backend/app/evaluation/public_runner.py`、`public_dataset.py`、`eval_metrics.py`、`baselines.py`、`backend/app/routes/evaluation.py`、`scripts/evaluation/*.sh`。

## 1. 评测对象与范围

| 项 | 内容 |
|----|------|
| 评测对象 | 文档 RAG 三类能力：检索（gold 物理页召回）、引用（答案引用页判对）、答案（分型判分） |
| 评测集 | `public_nist`（默认）：NIST AI RMF 公开评测集 v1，18 题（16 answerable + 2 unanswerable），见 `docs/DATA_CARD.md` |
| 保留 profile | `synthetic_smoke`：旧内嵌 22 条中英问答（`backend/app/evaluation/dataset.json` + `runner.py`），离线冒烟用 |
| 基线 | bm25 + lexical-rerank + extractive-answer（无密钥确定性基线，`baselines.py`） |
| 边界 | 本轮只跑工程基线；真实适配器（Docling/bge-m3/reranker/LLM）provenance 一律 NOT_RUN（见 BENCHMARK_CARD §10） |

## 2. 数据集生命周期（prepare → run → verify）

```text
download（DOI → 临时文件 → 尺寸 + SHA-256 双重校验 → rename 落盘）
  → extract_pages（pypdf 按物理页提取）
  → build_corpus（每物理页 1 chunk，从 content_start_page 起，不含任何 gold 信息）
  → validate_questions（fail-closed：evidence 逐字落在指定物理页；unanswerable 关键词全文零命中）
  → 原子写 work/eval_corpus.json（manifest_id + version 随行，供后续版本校验）
  → run（加载语料 → 基线预测 → 指标 + CI + 切片 → 报告 JSON 原子写入）
  → verify（复验语料、gold 与报告完整性）
```

- 命令：`python -m app.evaluation.public_runner --work-dir <dir> {prepare|run|verify}`，或宿主脚本 `scripts/evaluation/{download.sh,prepare.sh,run.sh} [WORK_DIR]`（默认 `<repo>/work`）。
- 下载失败即删除半成品，不留下不完整 PDF（`public_dataset.download_file`）。
- 缓存语料与 manifest 的 `id/version` 不一致时 `load_corpus` 拒绝运行并提示重新 prepare（409 语义见 §7）。

## 3. Gold 隔离硬规则（不可违反）

1. **gold 绝不进入检索/生成管线**：基线接口只接收 corpus 与 query（`run_baseline(corpus, questions)` 内仅用 `q["query"]`）；守护测试 `test_public_evaluation.py::test_baseline_never_receives_gold`。
2. **语料不含 gold**：`build_corpus` 产物只有 `document_id / physical_page / text`；`work/eval_corpus.json` 与报告均不含证据/答案字段。
3. **fail-closed 校验**：`validate_questions` 任何一条 evidence 不在指定物理页、或 unanswerable 关键词在全文命中，数据集即不合格（抛异常终止），不进入评测。
4. **manifest 不可变**：增删题目/改 gold 必须升 `manifest.version`；缓存语料版本不符直接拒绝（`load_corpus`）。
5. 报告内 `per_query.answer_detail` 只含打分过程（matched 片段/数值/点数），不含完整 gold 文本——gold 全文仅存于 `questions.jsonl`。

## 4. 指标计算协议（eval_metrics.py，与 BENCHMARK_CARD §2 一致）

1. **检索指标**（recall/precision/hit/hard_negative_recall@K、MRR、nDCG@K）：按题计算，宏平均；**只对 answerable 题平均**（unanswerable 无 gold 页，恒 0，不稀释）→ `retrieval_eligible / retrieval_total`。
2. **引用指标**：引用按去重后的 `(document_id, physical_page)` 元组计数；`citation_page_precision` 仅对带引用的题平均（`citation_page_precision_eligible`）；`hard_negative_citation_rate` 为全量聚合（硬负引用数 / 引用总数）。
3. **答案判分**：
   - exact：归一化后与任一 `gold_answers` 全等；
   - set：预测词集与 gold 集 F1，`F1=1.0`（gold 全集覆盖）判对；
   - rubric：`rubric.points` 逐点子串命中 ≥ `min_points` 判对；
   - numeric：答案中任一数字落入容差（相对：`abs(v−gold) ≤ tol×gold`；绝对：`abs(v−gold) ≤ tol`）；
   - unanswerable：**`no_answer=true 且 答案为空 且 无引用`** 才判对，三项缺一即 0 分。
4. **Eligibility**：非弃答题给出非空答案 → `answer_eligible=true`；`eligible/total` 为可评答案题数/全部题数（含 unanswerable）。
5. **CI**：均值类指标 bootstrap 95% CI（seed=0、1000 次重采样）；比例类同时给 Wilson CI（`wilson_ci(successes=round(sum(vals)), n)`）。
6. **切片**：`language / answer_type / tag / document` 四维；tag 取每题 `tags[0]`，document 取首个 gold 页文档（unanswerable 归入 `"unanswerable"` 组）。

## 5. Provenance 报告要求

报告必须携带 `provenance` 四适配器状态，状态只能是 `VERIFIED`（该适配器在当次运行中真实执行且可验证）或 `NOT_RUN`（未执行，需注明原因）：

| 适配器 | 状态 | 说明 |
|--------|------|------|
| docling | NOT_RUN（本轮） | 语料用 pypdf 提取；真实 Docling 已在 WSL 实测通过（非本轮评测链路） |
| embedding_bge_m3 | NOT_RUN（本轮） | 无真实权重环境/授权 |
| reranker_bge | NOT_RUN（本轮） | 同上 |
| llm | NOT_RUN（本轮） | 无密钥/成本/外传授权 |

规则：**mock 结果不得冒充真实模型验证**；任何报告须能由 `provenance` 字段一眼区分「工程基线结果」与「真实链路结果」。真实适配器验证后改标 `VERIFIED` 并记录验证命令与产物。

## 6. 执行方式

### 6.1 本地（WSL 原生，默认路径）

```bash
cd backend
# 一次性准备（下载+校验 PDF、构建语料、验证 gold）
bash ../scripts/evaluation/prepare.sh          # 默认工作目录 <repo>/work
# 运行评测（确定性报告）
bash ../scripts/evaluation/run.sh
# 复验（无独立脚本，直接调子命令）
./.venv/bin/python -m app.evaluation.public_runner --work-dir ../work verify
```

- Python 选择顺序：`VENV_PY` 环境变量 > `backend/.venv` > `python3`（三个脚本一致）。
- 输出：`work/eval_corpus.json` + `work/eval_reports/public_nist_report.json`（原子写入）。

### 6.2 Web 评测

- 通过 `POST /api/v1/evaluation/run` 走 Web 评测时，后端读 `work/eval_corpus.json`；未 prepare 返回 409（见 §7）。

## 7. 失败处理

| 场景 | 行为 | 依据 |
|------|------|------|
| `POST /evaluation/run` 且 `public_nist` 未 prepare（无 `work/eval_corpus.json`） | **409**，detail 提示先运行 `scripts/evaluation/prepare.sh` | `routes/evaluation.py` |
| 缓存语料与 manifest 版本不符 | 409，detail 提示重新 prepare | `routes/evaluation.py` → `public_runner.load_corpus` |
| 未知 profile | 400（可用 `public_nist`、`synthetic_smoke`） | `routes/evaluation.py` |
| 下载尺寸或 SHA-256 不符 | 抛异常终止并清理 .part 临时文件 | `public_dataset.download_file` |
| gold evidence 不在指定物理页 / unanswerable 关键词全文命中 | prepare 阶段抛异常终止 | `public_dataset.validate_questions` |
| 评测中异常 | 报告不落盘（原子写入，tmp 后缀重命名） | `public_runner.cmd_run` |

## 8. 确定性要求

- 同一输入重复运行两次，报告（去除 `created_at` 后）必须字节一致；每次 `run` 自动执行该自检并写入 `determinism: {verified, method}`。
- 随机源全部固定：bootstrap `seed=0`、排序 tie-break 固定、无网络依赖、无并发。
- 报告落盘用「临时文件 + `os.replace`」原子写入，失败不留半截文件。

## 9. 报告产物约定

| 产物 | 路径 | 内容 |
|------|------|------|
| 语料 | `work/eval_corpus.json`（JSONL） | manifest_id/version、文档清单、103 chunk、排除页数 |
| 报告 | `work/eval_reports/public_nist_report.json` | profile/manifest/corpus/baseline/metrics/ci/slices/per_query/provenance/created_at/determinism |
| 历史 | `evaluations` 表（SQLite） | 每次 API 评测的 config_json + metrics_json |
| 分析 | `work/analysis/NIST.AI.*.pages.json` | 制卡期人工核对用的按页文本转储（非评测产物） |
