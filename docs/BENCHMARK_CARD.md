# DocRAG Benchmark Card（public_nist v1）

> 本次文档更新，数据核对日期 2026-08-21。§3–§11 数字唯一权威来源：`work/eval_reports/public_nist_report.json`（2026-08-21 于 WSL 复跑再生成，指标与 2026-08-12 原报告一致，`determinism.verified=true`）；§12 数字唯一权威来源：`work/real_full_report.json`（created_at `2026-08-21T07:00:09`）、词法口径 run `work/real_full_lexical.json`（created_at `2026-08-21T10:40:04`）及三次单变体复跑 `work/real_full_{bm25,hybrid,rerank}.json`。口径定义与代码 `backend/app/evaluation/eval_metrics.py`、`baselines.py`、`public_runner.py`、`real_full_runner.py` 核对一致。

## 1. 任务定义

评测对象为「文档 RAG」三类能力，同一次运行产出：

| 能力 | 评测内容 | 判对口径 |
|------|----------|----------|
| 检索（retrieval） | top-K 是否召回 gold 物理页 | `(document_id, physical_page)` 元组命中 |
| 引用（citation） | 答案携带的引用页是否落在 gold 页 | 同上，按去重后引用元组计 precision/recall |
| 答案（answer） | 生成文本是否命中标准答案 | 按 answer_type 分型判分（见 §4） |

- 语料：2 份 NIST PDF、103 chunk（每物理页 1 个，从 content_start_page 起）、258,451 字符（见 DATA_CARD §6）。
- 查询规模：18 题（16 answerable + 2 unanswerable），全部 test split。
- 基线：**bm25 + lexical-rerank + extractive-answer**（纯 Python/stdlib，无密钥、无模型权重；`baselines.py`）。

## 2. 指标定义与口径（eval_metrics.py）

| 指标 | 定义 | 说明 |
|------|------|------|
| recall@K | \|gold ∩ top-K\| / \|gold\| | 宏平均（先算每题再平均） |
| precision@K | \|gold ∩ top-K\| / K | 同上 |
| hit@K | 每题 top-K 是否命中 gold（0/1） | 均值即 Hit Rate |
| hard_negative_recall@K | top-K 中 hard-negative 页占比 | 分母为全库 hard-negative 集合（`_hard_negatives`：其他题 gold 页中「同文档错页 ∪ 跨文档」） |
| MRR | 首个 gold 命中位置的倒数 | 未命中记 0 |
| nDCG@K | DCG/IDCG（K=max(ks)=5） | gold 集合内每命中位贡献 1/log2(i+2) |
| citation_page_precision | 去重后引用元组中 gold 占比（仅对有引用的题平均） | 分母是引用页数，非 top-K |
| citation_recall | 去重后引用元组命中 gold 的比例（\gold ∩ citations\ / \gold\） | |
| hard_negative_citation_rate | 引用中 hard-negative 元组数 / 引用元组总数 | 全量聚合 |
| answer EM | 答案判对（exact 全等 / set F1=1 / rubric 命中≥min_points / numeric 容差内 / 弃答正确） | eligible 题均值 |
| answer F1 | set/rubric 的 F1；exact/numeric 判对记 1.0 | eligible 题均值 |
| unanswerable_correct | 弃答题判对率 | 判对 = `no_answer=true 且 答案空 且 无引用` |

**Eligibility 规则**（见 EVALUATION_PROTOCOL §5）：

- 检索类指标只对 **answerable** 题平均（unanswerable 无 gold 页恒 0，不稀释）→ `retrieval_eligible=16 / retrieval_total=18`。
- 答案类指标按 `answer_eligible` 平均（非弃答题给出非空答案才 eligible）→ `eligible=16 / total=18`。
- CI：均值类用 bootstrap（固定 seed=0、1000 次重采样）；比例类同时给 Wilson 区间（`build_ci` 对每个指标都输出两种）。

## 3. 总体结果（metrics 段）

| 指标 | 值 | 95% CI（bootstrap / wilson） |
|------|-----|------------------------------|
| recall@1 | 0.6250 | [0.4062, 0.8438] / [0.3864, 0.8152] |
| precision@1 | 0.6875 | [0.4375, 0.8750] / [0.4440, 0.8584] |
| hit@1 | 0.6875 | [0.4375, 0.8750] / [0.4440, 0.8584] |
| recall@3 | 0.7188 | [0.5000, 0.9062] / [0.5050, 0.8982] |
| hit@3 | 0.7500 | [0.5000, 0.9375] / [0.5050, 0.8982] |
| recall@5 | 0.8438 | [0.6867, 1.0000] / [0.6398, 0.9650] |
| hit@5 | 0.8750 | [0.6875, 1.0000] / [0.6398, 0.9650] |
| MRR | 0.7469 | [0.5468, 0.9375] / [0.5050, 0.8982] |
| nDCG@5 | 0.7539 | [0.5702, 0.9161] / [0.5050, 0.8982] |
| hard_negative_recall@1 | 0.0083 | [0.0000, 0.0208] / [0.0000, 0.1936] |
| hard_negative_recall@3 | 0.0381 | [0.0208, 0.0601] / [0.0111, 0.2833] |
| hard_negative_recall@5 | 0.0676 | [0.0428, 0.0923] / [0.0111, 0.2833] |
| citation_page_precision | 0.1875（eligible 16 题均带引用） | — |
| citation_recall | 0.8438 | — |
| hard_negative_citation_rate | 0.2000 | — |
| answer EM | 0.0625（16 题中仅 nist-012 判对） | — |
| answer F1 | 0.0703 | — |
| unanswerable_correct | 0.0000（2 题均未正确弃答） | — |
| eligible / total | 16 / 18 | retrieval: 16 / 18 |

## 4. 答案分型结果（per_query + answer_type 切片）

| 类型 | 题数 | recall@1 | recall@5 | MRR | nDCG@5 | answer EM | 说明 |
|------|------|----------|----------|-----|--------|-----------|------|
| exact | 4 | 0.750 | 1.000 | 0.800 | 0.8467 | 0.000 | 抽取式句子与标准答案全等要求过高，4 题全未全等 |
| set | 6 | 0.4167 | 0.8333 | 0.625 | 0.6769 | 0.000 | F1=1.0（gold 全集覆盖）几乎不可达；nist-005 得最高 F1=0.125 |
| rubric | 4 | 0.625 | 0.625 | 0.750 | 0.6533 | 0.000 | 抽取句子覆盖点数不足（004: 0/2，006: 0/13，013: 0/3，016: 0/3） |
| numeric | 2 | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | nist-012（300±15%）判对；nist-007（1e9±1000%）抽取句未含数字 |
| unanswerable | 2 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 见 §7 弃答 0.0 原因 |

per_query 关键记录：18 题中唯一 `answer_correct=1.0` 的是 nist-012（数值 300，容差 ±15% 命中）；nist-004（rubric，风险定义）retrieval 全 K 为 0（最难的检索失败样本）。

## 5. 切片结果（slices 段）

| 切片 | 组（题数） | recall@1 | recall@5 | MRR | nDCG@5 | 备注 |
|------|-----------|----------|----------|-----|--------|------|
| language | en（15） | 0.600 | 0.8333 | 0.730 | 0.7374 | citation_recall 0.8333 |
| language | zh（3） | 0.3333 | 0.3333 | 0.3333 | 0.3333 | 2 条跨语言 + 1 条 unanswerable；answer_em 0.0 |
| document | NIST.AI.100-1（8） | 0.5625 | 0.6875 | 0.650 | 0.6250 | citation_recall 0.6875 |
| document | NIST.AI.600-1（8） | 0.6875 | 1.000 | 0.8438 | 0.8827 | citation_recall 1.0 |
| tag | framing（2） | 0.000 | 0.500 | 0.100 | 0.1934 | 最弱标签组（含最难题 nist-004） |
| tag | confabulation（1） | 0.000 | 1.000 | 0.250 | 0.4307 | recall@5 才命中 |
| tag | appendix-b（2） | 0.750 | 0.750 | 1.000 | 0.8066 | 页码跨 43/44 两页仍全中 |

## 6. 基线方法（baselines.py，可复现工程基线）

1. **BM25 检索**：k1=1.5、b=0.75，每页一个 chunk 为文档；检索 top-15（`rerank_top_k × 3`）。
2. **词法重排**：`BM25 分 × (1 + 查询词命中率)` 小幅调制，tie 保持 chunk 序（确定性）。
3. **抽取式答案**：numeric 题提取数字；其余返回与查询词重合度最高的句子（≤1000 字符）。
4. **引用**：top-5 全部作为 citation（无「只引被支撑页」过滤——这是 citation_page_precision 低的结构性原因）。
5. **弃答**：仅当无候选或 top chunk 与查询词零交集时 `no_answer=true`（对 unanswerable 题几乎不触发，见 §7）。
6. 全链路无随机源：tokenize 顺序、排序 tie、bootstrap seed 全部固定。

**2026-08-12 宿主复跑验证**：在独立工作目录复跑 `public_runner run`，全部指标、CI、切片、per_query 与仓库报告字节一致（仅 `corpus.source_cache` 路径字段因工作目录不同而异，`determinism.verified=true`）。

## 6.1 检索消融对比（2026-08-12 新增，ablation 段）

同一指标口径下四路检索变体的对比（答案生成均为抽取式；mock 稠密为**确定性 mock 嵌入**，与生产 mock 后端同源）：

| 变体 | 说明 | recall@1 | recall@5 | MRR | nDCG@5 | 引用召回 | 引用页精度 | 答案 EM | 答案 F1 |
|------|------|---------|---------|-----|--------|---------|-----------|---------|---------|
| bm25 | BM25 + 词法重排 | **0.625** | **0.844** | **0.747** | **0.754** | **0.844** | 0.188 | 0.062 | 0.070 |
| dense_mock | 纯 mock 稠密（无重排） | 0.344 | 0.594 | 0.440 | 0.469 | 0.594 | 0.138 | 0.062 | 0.077 |
| hybrid | RRF 混合（BM25+mock 稠密） | 0.500 | 0.750 | 0.641 | 0.663 | 0.750 | 0.175 | 0.062 | 0.077 |
| hybrid_rerank | 混合 + 词法重排 | 0.625 | 0.750 | 0.703 | 0.709 | 0.750 | 0.175 | 0.062 | 0.077 |

**解读（诚实口径，勿超读）**：
- mock 稠密向量在本语料上是弱信号（R@5 0.594 < BM25 0.844），符合预期——mock 嵌入是确定性哈希信号，不是语义嵌入；**这不能推广为真实 bge-m3 的能力结论**（真实嵌入 NOT_RUN）。
- 混合 + 重排（生产管线同构）恢复 R@1 到 BM25 水平，MRR 0.703 略低于纯 BM25——说明当前 mock 稠密对混合路的贡献有限且引入噪声；真实嵌入下的消融是后续验证项。
- 答案 EM/F1 各变体几乎无差异：答案质量瓶颈在抽取式答案器（检索已能命中页码），与检索变体关系不大。

## 6.2 失败案例分析（主基线，2026-08-12）

| 题 ID | 语言/类型 | 问题（节选） | recall@5 | 失败原因 |
|-------|----------|--------------|----------|----------|
| nist-004 | en/rubric | According to the AI RMF, how is risk defined? | 0.0 | 抽象定义题：gold 页用词（"net expected negative impact"）与查询词（risk/defined）零重叠，词法检索无法召回 |
| nist-008 | zh/set | 根据 AI RMF，可信 AI 系统包含哪些特征？请列出全部七项 | 0.0 | 中文跨语言题：中文按字切分 + 无语义匹配，无法桥接 "trustworthy" 与「可信」 |
| nist-006 | en/rubric | Appendix B 中哪些 AI 特定风险是新增或加剧的 | 0.5 | 部分召回：答案跨多个页面（附录 B 多页分布），top-5 只覆盖部分 gold 页 |
| nist-u01/u02 | en/zh unanswerable | （两题均不可答，关键词全文零命中已校验） | 0.0 | 基线无显式弃答能力，检索仍返回候选 → 抽取式答案器强行产出句子 → 0 分；正确行为应是 no_answer（产品管线已实现，见 MATURITY_MATRIX §4） |

失败模式归纳：① 抽象/定义类问题（无词汇重叠）② 中文跨语言（无语义桥）③ 多页分布答案（top-5 截断）④ 弃答识别缺失。①②③ 指向真实语义嵌入/重排的验证价值；④ 是基线能力边界，产品链路已用 no-answer 机制覆盖。

## 7. 已知边界（文档化，勿超读）

| 边界 | 说明 |
|------|------|
| 词法基线对中文跨语言题的局限 | zh 切片 recall@1=0.3333 vs en 0.6000：中文按字切分、无语义匹配，跨语言题（nist-008 七特征、nist-013 模型坍缩）几乎无法召回；**不构成对真实 bge-m3 中文能力的结论**（embedding 适配器 NOT_RUN） |
| 弃答 0.0 的原因 | 基线弃答触发条件（无候选 / 查询词零交集）对 unanswerable 题不满足——检索总能返回 5 页候选且 top chunk 有词交集，抽取式答案器总是产出句子 → `no_answer=false` 且带引用 → 判 0 分。**基线无显式弃答能力**，2 题全部失败是预期行为 |
| citation_page_precision 低的结构性原因 | top-5 全量当引用（每题 citation_count=5），页面精度天然 ≤ 0.2；真实产品管线有「生成后引用缓冲校验」（无有效引用 → no_answer，见 MATURITY_MATRIX §4），评测基线刻意不含该过滤以便暴露检索/引用原始质量 |
| 样本量 | 18 题 / 103 chunk，CI 宽度大（如 recall@1 wilson [0.386, 0.815]），结论只对该语料成立，无跨语料泛化声明 |
| 数值容差口径 | 相对容差按 gold 值比例计算（`abs(v−gold) ≤ tol × gold`），非绝对区间（nist-007 ±1000% 实际接受 1e9–1e12） |
| hard negatives 依赖全题集 | hard-negative 集合由全部 18 题的 gold 页推导；增删题目会改变该组指标，跨报告对比需固定 manifest 版本（缓存语料版本校验已 fail-closed） |

## 8. Gold 隔离声明

- gold 仅作为评测输入：`baselines.BM25Retriever` 只接收 corpus；`run_baseline` 对每题只用 `q["query"]`；`public_dataset.validate_questions` 在 prepare 阶段 fail-closed 校验（evidence 必须在指定物理页、unanswerable 关键词全文零命中）。
- 守护测试：`test_public_evaluation.py::test_baseline_never_receives_gold`（断言基线接口签名不含 gold 字段）。
- 评测报告与 `work/eval_corpus.json` 均不含任何 gold 字段（语料只有 document_id/physical_page/text）。

## 9. 确定性

| 项 | 值 |
|----|----|
| 报告字段 `determinism.verified` | `true` |
| 方法 | 同输入重复运行两次，报告（去除 `created_at` 后）字节一致（`public_runner.cmd_run` 运行时自检） |
| 独立复跑 | 2026-08-12 宿主在 /tmp 工作目录复跑，指标字节一致（§6） |
| 随机源固定 | bootstrap seed=0、排序 tie-break 固定、无网络依赖 |

## 10. Provenance（真实模型链路状态）

报告 `provenance` 字段四适配器本轮全部 `NOT_RUN`：

| 适配器 | 状态 | 原因 |
|--------|------|------|
| Docling 真实解析 | NOT_RUN（评测语料） | 评测语料用 pypdf 提取（确定性优先）；**真实 Docling 解析已于 2026-08-12 在 acceptance 镜像容器内 VERIFIED**（48 页真实摄取，见 VALIDATION.md §4） |
| bge-m3 embedding | NOT_RUN | 无真实权重加载授权/环境（2.2GB 权重未装） |
| bge-reranker-v2-m3 | NOT_RUN | 同上 |
| LLM | NOT_RUN | 无密钥/成本/外传授权，按任务约束不读取密钥、不调用付费 API |

**本文档 §3–§9 全部数字 = 无密钥工程基线（bm25 + 词法重排 + 抽取式答案）的结果，不代表真实模型链路性能；真实模型链路结果见 §12。**

## 11. 真实模型链路 Run（2026-08-20，未收录为正式基线）

`work/public_nist_real_run.json`（created_at 2026-08-20）：使用真实嵌入（bge-m3）+ 真实 LLM（qwen3:4b via Ollama），但 **解析与重排存在 provenance 矛盾**，本 run 不作为正式基线收录。

### 11.1 Provenance（与实际链路的矛盾）

| 适配器 | provenance 声明 | 实际状态 | 矛盾说明 |
|--------|----------------|----------|----------|
| Docling 解析 | NOT_RUN | pypdf 轻量解析 | 与声明一致（确实未用 Docling） |
| bge-m3 embedding | RUN | 真实加载（hf_cache 路径已记录） | 无矛盾 |
| bge-reranker-v2-m3 | RUN | **实际为 mock 词重叠降级** | AGENTS.md 已知薄弱点："bge-reranker-v2-m3 仍为 mock 降级，真实重排与 HF 权重加载未测"；provenance 标 RUN 与事实不符 |
| LLM | RUN | 真实 qwen3:4b（Ollama） | 无矛盾 |

### 11.2 指标（仅供参考，非正式基线）

| 指标 | 值 | 对比 mock 基线（§3） |
|------|-----|---------------------|
| recall@1 | 0.8125 | mock 基线 0.6250 |
| recall@5 | 0.9375 | mock 基线 0.8438 |
| MRR | 0.90625 | mock 基线 0.7469 |
| nDCG@5 | 0.9068 | mock 基线 0.7539 |
| citation_recall | 0.8125 | mock 基线 0.8438 |
| answer EM | 0.2143 | mock 基线 0.0625 |
| answer F1 | 0.3046 | mock 基线 0.0703 |
| unanswerable_correct | 1.0 | mock 基线 0.0 |
| eligible / total | 14 / 18 | mock 基线 16 / 18 |

### 11.3 切片（语言 / 文档）

| 切片 | recall@5 | MRR |
|------|---------|-----|
| en（15 题） | 0.9333 | 0.9 |
| zh（3 题） | 0.3333 | 0.3333 |
| NIST.AI.100-1（8 题） | 0.875 | 0.8125 |
| NIST.AI.600-1（8 题） | 1.0 | 1.0 |

### 11.4 为什么不算正式基线

1. **reranker provenance 矛盾**：标 RUN 但实际 mock 降级，recall/MRR 提升可能部分来自 bge-m3 embedding 而非 reranker
2. **解析非 Docling**：用 pypdf 按页抽取，分块质量与 Docling 结构化分块不同
3. **无消融对比**：该 run 未跑 BM25 / dense_mock / hybrid 变体，无法归因各组件贡献
4. **determinism 未验证**：该 run 未做同输入重复运行字节一致性自检

**结论**：真实嵌入 + 真实 LLM 的检索质量（recall@5 0.9375）显著优于 mock 基线（0.8438）；归因消融已于 2026-08-21 补跑完成（真实 bge-m3 + 真实 bge-reranker + 真实 LLM 三变体，provenance 无矛盾），见 §12。简历可引用区间值 "recall@5 0.84–0.94" 并标注口径。

## 12. 真实模型全链路消融（2026-08-21，正式收录）

运行入口 `backend/app/evaluation/real_full_runner.py`（WSL 实测）。主报告 `work/real_full_report.json`（三变体同进程跑完）；`work/real_full_lexical.json`（词法口径 run：bm25 修正 + hybrid_lexical）；另各变体单独复跑一次（`work/real_full_{bm25,hybrid,rerank}.json`）作可复现性核验。

### 12.1 Provenance（无矛盾）

| 适配器 | 状态 | 说明 |
|--------|------|------|
| 语料/解析 | 与 mock 基线同源 | `work/eval_corpus.json`（pypdf 每页 1 chunk）；四变体共用同一语料，差异仅在检索/重排/生成，归因干净 |
| bge-m3 embedding | RUN（真实） | FlagEmbedding 本地权重 `BAAI/bge-m3`，dense 1024 维；103 chunk 编制约 220s |
| bge-reranker-v2-m3 | RUN（真实） | sentence-transformers CrossEncoder（CPU），加载约 9s，逐对打分 top-15→top-5 |
| 词法重排 | RUN | `baselines.LexicalReranker`（与生产 mock 重排同实现：排序分 × (1 + 查询 token 命中率)，保序小幅调制） |
| LLM | RUN（真实） | OpenAI 兼容云端端点（运行时配置；密钥经设置页/env 注入，报告不含密钥） |

与 §11（2026-08-20 run）的区别：本轮 reranker 为真实 CrossEncoder 加载运行，provenance 与事实一致。

### 12.2 四变体结果（同一 18 题、同一指标口径）

> bm25_real_llm 与 hybrid_lexical_llm 来自词法口径 run（`real_full_lexical.json`，10:40）；hybrid 两行来自主报告（07:00）。检索类指标跨 run 确定性成立；answer/citation 类受 LLM 采样影响（见 §12.4）。

| 变体 | recall@1 | recall@3 | recall@5 | hit@1 | MRR | nDCG@5 | answer EM | answer F1 | unanswerable | wall |
|------|---------|---------|---------|-------|-----|--------|-----------|-----------|--------------|------|
| bm25_real_llm | 0.6250 | 0.7188 | 0.8438 | 0.6875 | 0.7469 | 0.7539 | 0.2143 | 0.3016 | 1.0 | 178s |
| hybrid_real_llm | 0.6250 | 0.7812 | 0.8750 | 0.6875 | 0.7521 | 0.7730 | 0.2143 | 0.2851 | 1.0 | 219s |
| hybrid_lexical_llm | 0.6250 | 0.7812 | 0.8750 | 0.6875 | 0.7521 | 0.7747 | 0.3077 | 0.4050 | 1.0 | 163s |
| hybrid_rerank_llm | **0.8125** | **0.9062** | **0.9375** | **0.8750** | **0.9062** | **0.9051** | 0.3333 | 0.4501 | 1.0 | 1044s |

对比无密钥基线（§3）：recall@5 0.844→0.938，MRR 0.747→0.906，answer EM 0.063→0.333，unanswerable_correct 0→1.0。

### 12.3 消融归因（§6.1 / §11.4 遗留问题闭环）

1. **真实 bge-m3 的价值**：hybrid（无重排）recall@5 0.875，超过纯 BM25 的 0.844，且远超 mock 稠密单路 0.594（§6.1）——混合检索的价值在真实嵌入下成立，§6.1「mock 结论不可推广」的保留条款就此解除。
2. **词法重排在 hybrid 池上零增益**（同口径对比，2026-08-21 补跑）：hybrid + 词法重排 vs 无重排，MRR 0.7521→0.7521、recall@1/3/5 全持平、nDCG@5 仅 +0.002。生产 mock 重排的「排序分 × (1 + 命中率)」是保序小幅调制设计，在 RRF 融合序上调不动英文 NIST 语料的查询——**生产运行时配置 mock 重排等于白付重排步骤（无质量收益，也几乎无成本）**。
3. **神经重排是唯一有效重排**（§11.4 缺口闭环）：hybrid + bge-reranker，MRR +0.154（0.752→0.906）、recall@1 +0.19（0.625→0.812）、recall@5 +0.06（0.875→0.938）。§11 run 的提升不再有「来自 embedding 还是 reranker」的归因疑问。
4. **bm25 行口径修正**：初版 §12.2 的 bm25_real_llm（recall@5 0.531 / MRR 0.406）误用了 Jaccard 词法重排（纯词法排序推翻 BM25 统计序，正是 `baselines.py` docstring 警告的噪声模式）；统一为生产词法重排后 recall@5 0.844 / MRR 0.7469，与 §3 mock 基线 bm25 变体 MRR 0.7469 **完全一致**——检索链路确定性再获一次跨模型验证。
5. **LLM 生成 vs 抽取式**（对照 §3）：answer EM 0.063→0.333、F1 0.070→0.450；弃答 0→1.0（LLM 判断 + no-answer 机制共同作用）。
6. **成本**：rerank 变体 wall 时间 ×4.7（CPU CrossEncoder 逐对打分），无 GPU 时重排是主要延迟来源；词法重排零成本但零收益。

### 12.4 边界（勿超读）

- **answer 指标受 LLM 采样影响**：跨 run 的 EM/F1 有波动（如 bm25 变体 EM 0.25↔0.21）；citation_recall 同理（hybrid_lexical 0.75 vs hybrid_real 0.8125，源于两次 run 的弃答行为不同，非检索差异）。检索类指标（recall@k / MRR / nDCG）跨 run 完全一致——检索链路确定性成立，生成链路不承诺字节级可复现。
- 18 题 / 103 chunk 样本量小，CI 宽（见 §7），结论仅对该语料成立；「词法重排零增益」对该重排实现（保序调制设计）成立，不排除更强词法特征（如 BM25 特征交叉）能产生增益。
- 语料为 pypdf 按页抽取，非 Docling 结构化分块——解析质量不在本消融范围内（Docling 真实解析单独 VERIFIED，见 VALIDATION §4）。
- LLM 具体型号以运行时配置为准，answer 类指标不可跨 LLM 配置直接对比。
