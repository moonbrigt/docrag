# DocRAG 工程说明

DocRAG 是一套可本地部署、保留 PDF 页码与坐标溯源的文档问答系统。系统覆盖解析、结构化分块、混合检索、重排、流式生成、引用定位、质量评测和容器化部署。

## 1. 系统范围

| 项 | 内容 |
|----|------|
| 应用形态 | React 单页应用 + FastAPI API + 本地模型与存储 |
| 技术栈 | React 19、Vite、TypeScript、Tailwind CSS、FastAPI、Pydantic、Docling、FAISS、SQLite FTS5、pdf.js、Docker |
| 核心能力 | PDF 溯源、混合检索、RRF 融合、多语言重排、带引用回答、原文高亮 |
| 运行方式 | 默认离线 MOCK；可切换本地 Ollama 或 OpenAI 兼容接口 |

## 2. 技术架构

### 2.1 分层

```text
表现层（React SPA）
  → API 层（FastAPI）
  → 业务层（Parse → Index → Retrieve → Rerank → Generate → Citation）
  → 模型层（Docling / bge-m3 / bge-reranker / LLM）
  → 存储层（SQLite + FTS5 + FAISS + PDF 原件）
```

### 2.2 索引链路

PDF → Docling（`page_no` + `bbox`）→ HybridChunker 结构化分块 → bge-m3 嵌入 → SQLite 元数据与向量 BLOB → FTS5 与 FAISS 索引。

### 2.3 问答链路

Query → FAISS 稠密召回 + FTS5 关键词召回 → RRF(k=60) 融合 → bge-reranker-v2-m3 精排 → LLM SSE 流式回答 → citation 事件 → pdf.js 跳页与 bbox 高亮。

## 3. 关键决策与权衡

| 决策点 | 采用方案 | 选择依据 | 主要边界 |
|--------|----------|----------|----------|
| 页码溯源 | Docling `prov.page_no + bbox` | 解析阶段直接建立引用与原文坐标映射 | 复杂扫描件仍需 OCR 兜底 |
| 向量存储 | SQLite(BLOB) + FAISS | 单机自包含，部署与恢复简单 | 大规模数据需 IVF/PQ/HNSW 或外部向量库 |
| 关键词检索 | SQLite FTS5 trigram | 中英子串检索，无额外服务 | 1–2 字中文需要 LIKE 兜底 |
| 融合策略 | RRF(k=60) | 无需标定 cosine 与关键词分数 | 未针对特定语料调权 |
| 重排 | bge-reranker-v2-m3 | 本地、多语言、无外部 API 成本 | 首次加载与 CPU 推理耗时较高 |
| LLM 接入 | openai SDK + `base_url` | Ollama 与 OpenAI 兼容接口共用调用层 | 不同后端的输出稳定性需分别评测 |
| PDF 预览 | pdf.js + 归一化 bbox | 浏览器端渲染且保留文本层 | bbox 缺失时降级为整页定位 |
| 身份与 ACL | Principal（租户/用户/组）+ 可信反向代理头注入 | 本地部署无认证体系时仍可隔离租户与权限；浏览器无法伪造 `X-Rag-*`（CORS 白名单不含） | 无内置认证（OIDC 属产品决策）；信任边界=反向代理 |
| 生命周期状态机 | queued→…→indexed + warning/failed/cancelled，原子认领 | cancel/retry 无竞态；document_events 全量审计 | 取消无法强杀进行中的 Docling 原生解析线程 |
| 版本策略 | source_id + version，索引成功才 promote | 失败的新版本不污染线上（旧版保持 active） | 无回滚操作（归档保留，回滚属产品决策） |
| 无答案语义 | 缓冲校验 + no_answer(no_evidence/not_supported) | 无支撑内容绝不泄出；LLM 不因无证据被调用 | 低证据阈值展示未做（产品决策） |
| 评测基线 | 无密钥确定性基线（BM25+词法重排+抽取式） + bootstrap/Wilson CI + 切片 | 零密钥可复现、有置信边界；报告含 provenance 明示真实模型 NOT_RUN | 词法基线无弃答能力、中文跨语言召回弱（zh recall@1 0.333，见 BENCHMARK_CARD） |

## 4. 工程约束

- API、数据模型、页面和验收标准由 `docs/SPEC.md` 统一约束。
- 后端按 routes → services → repositories → core 分层，入口不承载业务逻辑。
- `chunks.page_no` 必填；bbox 统一为 top-left 原点下的 `left/top/right/bottom` 归一化坐标。
- SQLite 写操作经单连接与 `asyncio.Lock` 串行化，避免并发写损坏。
- 前端颜色来自设计 Token，图标统一使用 Lucide，并支持暗色与亮色主题。
- 模型不可用时必须显式报告状态，真实检索链路不静默降级。
- **ACL fail-closed**：无权限一律 404 / 空结果，不泄露文档存在性；检索双路（FAISS/FTS）均在范围内过滤。
- **评测 gold 隔离**：gold 只作评估输入，绝不进入检索/生成管线（有守护测试）；真实模型验证状态以 provenance 字段标注 VERIFIED/NOT_RUN，mock 结果不得冒充真实验证。

## 5. 已实现能力

- PDF 上传、异步状态机（8 态）、Docling 解析与结构化分块。
- FAISS 稠密召回、FTS5 关键词召回、RRF 融合与可选重排。
- Ollama / OpenAI 兼容双后端及 SSE 流式生成（stage/delta/citation/no_answer/done/error 事件）。
- citation 事件（含 sourceId/version/title/createdAt）、完整 PDF 文件端点、页码跳转与 bbox 高亮、JSON v1 答案导出。
- 文档列表、详情、删除及向量与 FTS 同步清理。
- 生命周期：cancel / retry（原子认领）/ 版本替换（promote 后归档）/ 重启恢复。
- ACL：租户 + 属主/组/管理员，可信反向代理身份注入，检索范围与 trace 访问控制。
- 反馈与追踪：feedback 表、`GET /trace/{id}`（query 原文不落库）。
- 版本化评测：public_nist（18 题 NIST 公开语料）+ synthetic_smoke（22 条），CI/切片/provenance/确定性报告。
- nginx 前端、FastAPI 后端、SQLite/模型持久卷组成的 Docker Compose 部署（含隔离验收栈 docrag-acceptance）。

## 6. 验证状态

| 检查 | 当前结果 |
|------|----------|
| 后端测试 | **61 个测试项通过**（2026-08-12 复核，含 4 个成熟度测试文件与公开评测测试） |
| 前端静态检查 | ESLint 零告警、TypeScript/Vite 构建通过 |
| Docker | 验收栈 `docrag-acceptance` 构建并 healthy（backend/frontend 镜像见 VALIDATION.md §4）；容器内 pytest 61 passed、public_nist 评测与宿主一致 |
| HTTP 链路 | 首页、健康检查、PDF 文件、SSE citation、no_answer、feedback、trace、版本、ACL 已验证 |
| 评测 | 无密钥基线指标 + bootstrap/Wilson CI + 四维切片，报告确定性字节一致（复跑验证） |
| bbox 契约 | TOPLEFT/BOTTOMLEFT 转换、按页归一化、边界夹取有回归测试 |

## 7. 已知边界

- 默认 Compose 使用确定性 MOCK，真实 Docling、bge-m3、reranker 与本地 LLM 的组合链路尚未完成同等强度的端到端验证（provenance 全部 NOT_RUN）。
- 无内置认证（OIDC/SSO 未实现）：身份由可信反向代理注入，多租户生产方案需产品决策。
- 当前为单 SQLite 连接设计，未实现限流与横向扩展。
- FAISS 使用内存平面索引，适合当前数据规模；百万级以上需要更换索引结构或存储方案。
- 深度 OCR、多轮对话、自动纠错回路和跨文档多跳推理不在当前范围内。
- 评测基线为词法基线：无弃答能力（unanswerable_correct=0.0）、中文跨语言召回弱（zh recall@1 0.333），不代表真实模型链路性能。

## 8. 后续方向

- 增加真实模型环境下的固定评测基线（各适配器从 NOT_RUN 转 VERIFIED）与性能数据。
- 增加扫描件 OCR 与复杂布局回归样本。
- 完善前端引用跳转与 SSE 解析的自动化测试。
- 根据数据规模评估 IVF/PQ/HNSW 与外部向量存储。
- 评测回归门禁（跨报告 diff）与多轮对话上下文（产品决策项）。
