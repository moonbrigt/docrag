# DocRAG 数据卡（NIST AI RMF 公开评测集 v1）

> 本次文档更新，数据核对日期 2026-08-12。数据源（唯一权威）：`backend/app/evaluation/datasets/nist_ai_rmf_public_v1/manifest.json` 与 `questions.jsonl`；报告侧交叉核对 `work/eval_reports/public_nist_report.json`。

## 1. 数据集标识

| 项 | 值 |
|----|----|
| 数据集 id | `nist_ai_rmf_public_v1` |
| 名称 | NIST AI RMF 公开评测集 v1（自建问题与页码 gold） |
| profile | `public_nist`（`POST /evaluation/run` 的默认 profile） |
| 版本 | 1.0.0（created_by: `docrag-dataset-eval`，created_at: 2026-08-12） |
| 规模 | 18 题（16 answerable + 2 unanswerable），split: test 18 / dev 0 / train 0 |

## 2. 来源文档（manifest.sources）

| 项 | NIST.AI.100-1 | NIST.AI.600-1 |
|----|---------------|---------------|
| 文件名 | `NIST.AI.100-1.pdf` | `NIST.AI.600-1.pdf` |
| 名称 | 人工智能风险管理框架（AI RMF 1.0） | 生成式 AI 跨部门配置文件（GAI Profile） |
| 页数（物理） | 48 | 64 |
| 大小 | 1,946,127 bytes | 1,174,643 bytes |
| SHA-256 | `7576edb531d9848825814ee88e28b1795d3a84b435b4b797d3670eafdc4a89f1` | `6e73620ab6b64e90ef2c04bf0e0d6246185a2f4b1b13cab0df494496cff89b6a` |
| DOI | https://doi.org/10.6028/NIST.AI.100-1 | https://doi.org/10.6028/NIST.AI.600-1 |
| 许可 | NIST Open License（美国政府公共领域作品，可自由使用/再分发），https://www.nist.gov/open/license | 同左 |
| 正文起始物理页（content_start_page） | 6 | 5 |

**物理页 ↔ 印刷页映射（manifest.physical_page 字段，人工核对）**：

- `NIST.AI.100-1`：physical_page 为 1 起算（含封面）；正文印刷页码 `printed = physical − 5`（物理 p6 = 印刷 p1）；罗马序页 i/ii 对应物理 p4/p5；物理 p1–p3 无印刷页码（封面/版权页/公告页）。
- `NIST.AI.600-1`：`printed = physical − 4`（物理 p5 = 印刷 p1）；物理 p1–p4 无印刷页码（封面/标题页/About 页/目录页）。

## 3. 问题统计（questions.jsonl 全量核对）

### 3.1 总体分布

| 维度 | 分布 | 题号 |
|------|------|------|
| answerable / unanswerable | 16 / 2 | answerable: nist-001…016；unanswerable: nist-u01, nist-u02 |
| 语言 | en 15 / zh 3 | zh: nist-008, nist-013（跨语言）+ nist-u02（unanswerable） |
| 答案类型 | exact 4 / set 6 / rubric 4 / numeric 2 / unanswerable 2 | exact: 001,003,009,014；set: 002,005,008,010,011,015；rubric: 004,006,013,016；numeric: 007,012 |
| 按文档 | NIST.AI.100-1: 8 题（001–008）；NIST.AI.600-1: 8 题（009–016）；unanswerable: 2（跨文档无关） | |

### 3.2 答案类型细则

- **exact**（4 题）：归一化（NFKC + 去连字符 + 空白折叠 + 小写）后与 `gold_answers` 全等；每题 1–3 个别名答案。
- **set**（6 题）：预测答案的词集合与 gold 集合算 precision/recall/F1，`F1=1.0`（gold 全集覆盖）才算对。
- **rubric**（4 题）：`rubric.points` 逐点子串命中，命中数 ≥ `min_points` 算对；`min_points` 分别为 004→2、006→3（13 点）、013→2（3 点）、016→2（3 点）。
- **numeric**（2 题）：`numeric.value` + 相对容差：nist-007 gold=1e9、容差 ±1000%（接受 1e9–1e12，对应原文 "billions or even trillions"）；nist-012 gold=300、容差 ±15%（接受 255–345，原文 "300 round-trip flights"）。
- **unanswerable**（2 题）：判分规则见 EVALUATION_PROTOCOL §5.2；两题均已通过全文关键词扫描验证与文档无关（`unanswerable_keywords` 在两份 PDF 全文零命中，程序化校验，见 `public_dataset.py:validate_questions`）。

### 3.3 hard negatives（刻意构造）

- **跨文档同页号**：gold 以 `(document_id, physical_page)` 元组标识，跨文档同页不算命中（nist-001 与 nist-009 等成对出现）。
- **同文档错页**：同一文档不同题引用不同页，检索返回的错页属于 hard negative。
- hard negative 集合由程序计算（`eval_metrics._hard_negatives`：其他题 gold 页中「同文档错页 ∪ 跨文档」），并产出 `hard_negative_recall@K` 与 `hard_negative_citation_rate` 指标。

### 3.4 标签（tag 切片维度，14 个）

appendix-b(2)、background(1)、bias(1)、confabulation(1)、core(1)、environmental(1)、framing(2)、out-of-scope(2)、pwg(1)、risk-dimensions(1)、security(1)、synthetic-data(1)、tevv(1)、trustworthiness(2)；另含 cross-lingual（nist-008/013）、legal、definition、scale、structure、comparison 等辅助标签。

## 4. Gold 结构

每题字段（JSONL 一行一题）：

| 字段 | 说明 |
|------|------|
| `id` | 题号（nist-001…016 / nist-u01, u02） |
| `query` | 问题原文（en/zh） |
| `answer_type` | exact / set / rubric / numeric / unanswerable |
| `gold_answers` | 标准答案（unanswerable/rubric 为空） |
| `gold_pages[]` | `{document_id, physical_page, printed_page, evidence}`——证据定位到**物理页**，`evidence` 为 pypdf 提取文本中逐字存在的原文片段（归一化后子串匹配，`public_dataset.py:validate_questions` 程序化 fail-closed 校验） |
| `rubric` / `numeric` | rubric 计分点与 min_points；数值题值与容差（见 §3.2） |
| `language` / `tags` / `split` | 语言、标签、划分（全部 test） |
| `unanswerable` / `unanswerable_keywords` | 弃答题标记与全文零命中关键词 |

## 5. 明确声明

1. **不是 NIST 官方 benchmark**：问题、gold 答案与页码映射均为本项目自建（`created_by: docrag-dataset-eval`），NIST 未背书任何问答对；任务背景中的 22 条旧手写问答归入 `synthetic_smoke` profile，与公开评测集严格分离。
2. **样本小、无泛化结论**：18 题 / 112 页，题目侧重风险定义、结构清单与关键事实；不构成对任意 RAG 系统在任意文档上 OCR/解析泛化能力的结论（manifest.notes 第 3 条原文声明）。
3. **许可与再分发**：NIST Open License 允许自由使用/再分发；仓库出于**体积控制**不提交 PDF 大文件，只含下载器、manifest、SHA-256 与 gold（`scripts/evaluation/download.sh` 从 DOI 确定性下载并做 SHA-256 + 尺寸双重校验，缓存于 `work/source_cache/`，该目录已入 `.gitignore`）。
4. **gold 隔离**：gold 数据绝不进入检索/生成管线——baseline 只接收 corpus + query（`baselines.py` / `public_runner.run_baseline`），并有专门测试 `test_public_evaluation.py::test_baseline_never_receives_gold` 守护。

## 6. 语料统计（报告 cross-check）

| 项 | 值（public_nist_report.json corpus 段） |
|----|------|
| 文档 | NIST.AI.100-1、NIST.AI.600-1 |
| chunk 数 | 103（每物理页 1 个 chunk，从 content_start_page 起） |
| 字符数 | 258,451 |
| 排除页 | 9（AI.100-1 前 5 页 + AI.600-1 前 4 页：封面/版权/目录等无正文页；gold 验证与 unanswerable 扫描仍覆盖全页） |

## 7. 已研究未采用的数据源

| 数据源 | 未采用原因 |
|--------|-----------|
| FinanceBench | 无明确 LICENSE |
| QASPER / LitQA2 | 无原始 PDF 页码 |
| MP-DocVQA | 不是 PDF 形式、体积过大 |
