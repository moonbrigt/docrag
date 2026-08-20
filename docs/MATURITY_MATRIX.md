# DocRAG 成熟度矩阵

> 面向「成熟文档知识产品」验收的逐维度审计表：每个维度标注实现状态、代码位置与证据，未实现项写明原因。
> 本次文档更新，数据核对日期 2026-08-12。事实来源：`backend/app/**`、`frontend/src/**`、`docker-compose.acceptance.yml`、`work/eval_reports/public_nist_report.json`（评测数字唯一权威）。
> 状态图例：✅ 当前有证据（基线已实现且有测试/运行证据）｜🆕 本次成熟度扩展实现｜⬜ 未实现且有原因｜❓ 需要产品决策。

## 1. 摄取状态机与进度

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| 摄取状态机（8 态） | 🆕 | `queued → parsing → chunking → embedding → indexed`，异常分支 `warning`（部分阶段成功、分块保留可检索）/ `failed`（清理 partial）/ `cancelled`（终态）。见 `backend/app/services/pipeline_service.py:run_pipeline`（阶段守卫 `_alive`）、`backend/app/repositories/document_repo.py:TRANSIENT_STATUSES/RETRYABLE_STATUSES/update_status`（每次流转写 `document_events` 审计）。前端 8 态徽标 `frontend/src/lib/status.ts:docStatusMeta` |
| 取消 / 重试（原子认领） | 🆕 | `POST /documents/{id}/cancel`（仅瞬态可取消，冲突 409）、`POST /documents/{id}/retry`（failed/warning/cancelled 原子认领回 queued，原文文件缺失 409），见 `backend/app/services/document_service.py:cancel_document/retry_document` + `document_repo.transition_status`；测试 `backend/app/tests/test_maturity_lifecycle.py` |
| 启动恢复 | 🆕 | 服务重启后瞬态文档 → `failed`（reason=`service_restart_interrupted`）并清理 partial chunks，见 `backend/app/main.py:lifespan` → `document_service.recover_interrupted`；测试 `test_maturity_lifecycle.py::test_restart_recovery` |
| 摄取进度（百分比） | ⬜ | 仅有状态级进度。Docling 解析在独立线程执行（`pipeline_service` 注释明确：取消无法强杀进行中的原生解析线程），无细粒度回调，无法给出可靠百分比——文档化限制 |
| 问答阶段进度 | 🆕 | SSE `stage` 事件（`retrieving / reranking / generating`）+ 前端 StageIndicator，见 `backend/app/routes/chat.py` 事件协议、`backend/app/services/generate_service.py:stream_answer` |

## 2. 文档生命周期与版本

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| 版本模型 | 🆕 | `documents` 表新增 `source_id / version / is_active / archived_at`：首版 `source_id=自身 id`、`version=1`；新版本 `version=MAX+1` 原子递增且 `is_active=0`；索引成功后 `promote_on_success` 归档旧 active 版（`backend/app/repositories/document_repo.py:insert_version/promote_version`、`backend/app/services/pipeline_service.py:_promote`） |
| 版本端点 | 🆕 | `POST /documents/{id}/versions`（202 + `{document_id, version, status}`）、`GET /documents/{id}/versions`（同 source 全版本，可见性过滤），见 `backend/app/routes/documents.py:create_version/list_versions`；前端 `VersionUploadDialog` + `Documents.tsx` 版本替换入口 |
| 版本约束 | 🆕 | 仅 active 版本可发起替换（409）；仅 owner/管理员可操作（`auth.doc_manageable`）；测试 `test_maturity_versions.py` |
| 删除一致性 | ✅ | 事务内清理 FTS + chunks + events + 文档行，随后重建 FAISS 并删物理文件（`backend/app/services/document_service.py:delete_document`）；防孤儿 chunk 竞态测试 `test_maturity_lifecycle.py::test_delete_race_no_orphan_chunks` |
| 版本回滚（一键切回旧版） | ⬜ | 版本替换后旧版被归档（`is_active=0`）但无「重新激活旧版」的管理操作；归档内容保留可查。需要产品决策是否提供回滚按钮 |

## 3. 来源范围与权限（ACL / 租户）

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| 身份模型（Principal） | 🆕 | `backend/app/auth.py`：`Principal(tenant_id, user_id, groups)`；管理员 = `user_id=="admin"` 或组含 `admins` |
| 可信反向代理身份注入 | 🆕 | 仅 `RAG_TRUSTED_PROXY=true` 时从 `X-Rag-Tenant / X-Rag-User / X-Rag-Group` 头解析身份，否则一律本地默认身份（default/local/无组）；见 `auth.get_principal` + `backend/app/config.py:TRUSTED_PROXY`。nginx 注入示例 `frontend/nginx.conf`（`X-Rag-Tenant "default"`、`X-Rag-User "demo"`），容器内默认开启（`docker-compose.acceptance.yml` 设 `RAG_TRUSTED_PROXY: "true"`） |
| 浏览器无法伪造身份 | 🆕 | CORS `allow_headers` 仅 `Content-Type, Authorization`，不含 `X-Rag-*`（`backend/app/main.py:_cors_origins` 下方中间件）；测试 `test_maturity_acl.py::test_cors_does_not_allow_x_rag_headers`、`::test_local_mode_ignores_identity_headers` |
| 可见性（fail-closed） | 🆕 | 无权限一律 404 / 空结果，不泄露存在性：租户匹配 +（属主 或 组成员重叠 或 管理员），见 `auth.doc_visible`；测试 `test_maturity_acl.py::test_acl_revoke_fail_closed`（撤权后立即 404） |
| 管理权限 | 🆕 | 删除 / ACL 修改 / cancel / retry / 版本替换需属主或管理员（`auth.doc_manageable`）；测试 `test_maturity_versions.py::test_versions_require_manage_permission` 等 |
| 检索范围 ACL | 🆕 | `resolve_scope`：`document_ids=None`=全部可见、`[]`=显式空范围（零结果）、其余=交集（`backend/app/services/document_service.py`）；FAISS/FTS 双路均限定范围（`retrieve_service.hybrid_retrieve` + `_faiss_scoped`/`_fts_search`），范围外条目绝不泄漏；测试 `test_maturity_acl.py::test_document_ids_scoped_both_retrieval_routes`、`::test_empty_document_ids_is_empty_scope` |
| ACL 端点与 UI | 🆕 | `GET/PUT /documents/{id}/acl`（`AclPayload{tenant_id, owner_user_id, groups}`，PUT 时 tenant_id 不可修改）；前端 `AclDialog`；仅 owner/管理员可改 |
| trace/feedback 访问控制 | 🆕 | `GET /trace/{id}` 仅同租户同用户或管理员可读（`trace_service.get_trace`），其余 404 |
| 认证（OIDC/SSO/登录页） | ⬜ | 无认证体系：身份由可信反向代理注入（单点信任模型）。生产需在网关层（企业 IdP / OIDC 代理）完成认证后注入身份头——**❓ 需要产品决策**：默认单用户（default 租户）无隔离，多租户认证方案需产品拍板 |

## 4. 引用与证据

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| 页码引用 + bbox 高亮 | ✅ | 基线已有：`citation` SSE 事件含 `page`/`bbox`、`/documents/{id}/file` 原 PDF、pdfjs 跳页高亮（`frontend/src/components/common/CitationChip.tsx`、`PDFPreview.tsx`） |
| 引用元数据扩展 | 🆕 | citation 事件新增 `sourceId / version / title / createdAt / processingMs`（`backend/app/services/citation_service.py:build_citations`，元数据由 `retrieve_service` join `documents` 表透传）；前端引用标签显示 `v{version}`（`frontend/src/lib/citation.ts:citationLabel`） |
| 零分候选不冒充证据 | 🆕 | `_has_signal`：faiss/fts 均无正分的候选不进证据列表（`backend/app/services/generate_service.py`）；测试 `test_maturity_chat.py::test_no_answer_no_evidence_llm_not_called` |
| 引用缓冲校验 | 🆕 | 生成内容整体缓冲，无有效引用则以 `no_answer(not_supported)` 收尾，**绝不泄出无支撑 delta**（`generate_service.stream_answer`）；引用编号越界跳过（`citation_service`）；测试 `test_maturity_chat.py::test_no_answer_not_supported_when_no_valid_citation` |
| 引用判对（评测口径） | 🆕 | 以 `(document_id, physical_page)` 元组判对，跨文档同页号不算命中（`backend/app/evaluation/eval_metrics.py:per_query_metrics`）；测试 `test_public_evaluation.py::test_cross_document_same_page_not_confused` |
| 引用去重与计数 | 🆕 | 按引用首次出现顺序去重（`citation_service.build_citations`）；指标 `citation_count / hard_negative_citations` 入 per-query 报告 |

## 5. 无答案 / 低证据状态

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| no_answer SSE 事件 | 🆕 | `{reason: "no_evidence"|"not_supported", evidence_candidates}`；`no_evidence`=检索后无有效信号（LLM 不调用），`not_supported`=有证据但生成无有效引用（`generate_service.stream_answer`）；前端 `NoAnswerCard` |
| 空知识库 / 无可见文档 | 🆕 | `/chat` 直接 409（不进 SSE），文案引导上传（`backend/app/routes/chat.py`）；测试 `test_maturity_chat.py::test_empty_kb_chat_409`、`test_search_eval.py::test_search_empty_kb` |
| 低证据阈值提示 | ⬜ | 无「证据分数低于阈值」的显式提示配置（证据分数随 citation/trace 透传，但未做阈值展示）。**❓ 需要产品决策**：是否暴露分数阈值与「低证据」展示策略 |
| 弃答评测 | 🆕 | 评测含 2 条 unanswerable 题，判分规则：`no_answer=true 且 答案为空 且 无引用` 才得分（`eval_metrics.py:score_answer`）；基线无弃答能力（`unanswerable_correct=0.0`，见 BENCHMARK_CARD §7） |

## 6. 对话体验

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| 阶段提示 | 🆕 | SSE `stage` 事件 + `StageIndicator`（retrieving → reranking → generating） |
| 停止生成 | 🆕 | 前端 Stop 按钮：中止消费 SSE 并标记 `stopped`（`frontend/src/pages/Chat.tsx:stop`） |
| 多来源检索范围 | 🆕 | `ScopePanel` 多选文档；请求 `document_ids` 与可见集取交集（见 §3） |
| 默认重排不可静默降级 | ✅ | `ChatRequest.rerank` 默认 `true`；rerank 未就绪 fail-closed（503/错误事件，不降级为截断），见 `routes/search.py`、`generate_service.stream_answer`；测试 `test_maturity_chat.py::test_rerank_fail_closed` |
| 后端选择器 | ✅ | `BackendSelector`（LLM/Embedding/Rerank 就绪状态来自 `/config/backends`） |
| 不可变来源清单 + JSON 导出 | 🆕 | 提问时刻保存不可变 source manifest，答案可导出 JSON v1（`docrag.answer-export.v1`：回答+trace 摘要+citations+source manifest），见 `frontend/src/lib/export.ts`、`MessageBubble.tsx`「导出 JSON」 |
| 多轮对话 | ⬜ | 单轮问答，无会话上下文延续（Spec §3 锁定「多轮 Agent/工具调用」不在 MVP 范围；`RecentChats` 仅本地历史列表）。**❓ 需要产品决策**：多轮上下文是否进入 v2 范围 |

## 7. 反馈与纠错

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| 反馈采集 | 🆕 | `POST /feedback`：`trace_id` + `rating(useful/not_useful)` + `issue_type(wrong_source/unsupported/stale/missing/bad_answer)` + `selected_text` + `comment`（`backend/app/schemas.py:FeedbackIn`，兼容 rating/useful 两种提交形式）；`feedback` 表（`backend/app/db.py`）；前端 `FeedbackPanel`；测试 `test_maturity_chat.py::test_trace_and_feedback_query_not_stored` |
| 追踪查询 | 🆕 | `GET /trace/{trace_id}`：evidence / citations / stage_timings / model_provenance（`TraceOut`，ACL 过滤见 §3） |
| 隐私契约 | 🆕 | query 原文与可反查哈希一律不落库，`query_hash` 固定 `"not_stored"`（`trace_service` / `trace_repo` / `generate_service` 三处注释一致） |
| 纠错闭环 | 🆕 | 人工纠错入口 = 版本替换（上传新版本替换旧内容，见 §2）+ 反馈标注；**自动纠错回路**（反馈驱动索引/答案调整）⬜ 未实现，有原因：需真实模型链路与运营数据支撑，超出本轮范围 |

## 8. 版本化评测

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| 公开评测集（自建 gold） | 🆕 | `public_nist` profile：两份 NIST PDF、18 题（16 answerable + 2 unanswerable），manifest 版本化（`id + version`，缓存语料不匹配即拒绝，见 `public_runner.load_corpus`）；数据卡见 `docs/DATA_CARD.md` |
| 指标 + CI + 切片 | 🆕 | Recall/Precision/Hit@K、MRR、nDCG@K、citation page precision/recall、hard-negative、answer EM/F1/数值容差、bootstrap(seed=0, n=1000) 与 Wilson CI、language/answer_type/tag/document 四维切片（`eval_metrics.py`）；报告 `work/eval_reports/public_nist_report.json`（数字见 `docs/BENCHMARK_CARD.md`） |
| 确定性 | 🆕 | 同输入重复运行两次，报告（去除 `created_at` 后）字节一致——运行时自检并在报告 `determinism.verified=true`（`public_runner.cmd_run`）；2026-08-12 宿主复跑确认指标字节一致 |
| API + UI | 🆕 | `POST /evaluation/run` 默认 `public_nist`（未 prepare 返回 409 并提示脚本）；`synthetic_smoke`（旧 22 条）保留；前端 `Evaluation.tsx` 双 profile 选择 + `EvaluationReport.tsx` |
| 真实模型评测 | ⬜ | 四个真实适配器（Docling / bge-m3 / bge-reranker / LLM）本轮全部 `NOT_RUN`（报告 `provenance` 字段）：无密钥/成本/外传授权与真实权重环境，按任务约束不读取密钥、不调用付费 API |
| 评测历史对比 / 回归门禁 | ⬜ | 报告按次落库（`evaluations` 表）可查历史，但无跨报告 diff 与自动回归门禁。**❓ 需要产品决策**：是否引入 CI 评测门禁 |

## 9. 延迟 / 取消 / 重试

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| 延迟观测 | 🆕 | 每轮问答 `stage_timings`（retrieving/reranking/generating/total ms）落 trace；进程指标直方图 `pipeline_latency_ms / retrieve_latency_ms / llm_latency_ms / http_request_latency_ms`（`core/metrics.py`） |
| 取消 / 重试 | 🆕 | 见 §1：原子认领、冲突 409、取消后清理 partial chunks；`retry` 前先确认原文文件存在（避免认领后卡 queued） |
| 取消的文档化限制 | 🆕 | 无法强杀进行中的 Docling 原生解析线程（线程在事件循环外），只能由阶段守卫停止后续阶段——`pipeline_service.py` 模块注释明示 |
| 请求超时 | ⬜ | nginx 侧 `proxy_read_timeout/send_timeout 3600s`（`frontend/nginx.conf`）为兜底；应用层无请求级超时/背压。**❓ 需要产品决策**：SSE 长连接超时策略（如生成超时上限） |

## 10. OCR / 布局 / 多语言

| 项 | 状态 | 实现与证据（代码位置） |
|----|------|----------------------|
| 深度 OCR（扫描件） | ⬜ | 未实现且有原因：MVP 聚焦可提取文本 PDF（Spec §3 明确不做「扫描件深度 OCR」）；评测语料为文本型 PDF，**无 OCR 评分**；真实 Docling OCR extra 路径未验证（provenance `NOT_RUN`）。市场对照：Google Document AI OCR 为托管服务，本地采用 Docling OCR extra 需另行评估 |
| 布局（结构化分块） | ✅ | Docling HybridChunker 结构化分块（`core/parser.py` 透传 `page_no`+归一化 `bbox`+`section`）；bbox 契约有回归测试（`test_parser.py::test_normalize_docling_bbox*`） |
| 复杂布局（多栏/跨页表格） | ⬜ | 真实 Docling 在本轮容器验收中未执行（`NOT_RUN`），复杂布局质量无实测证据；评测集含 Appendix B 跨页题（nist-006 跨物理页 43/44）作为回归样本 |
| 多语言（检索侧） | ✅ | bge-m3 dense+sparse 声明 100+ 语言；FTS 侧 1–2 字中文 LIKE 兜底（`retrieve_service._short_query`） |
| 多语言（评测实证） | 🆕 | 评测含 2 条中文跨语言题 + 1 条中文 unanswerable（zh 切片 3 题）：zh recall@1 = 0.333 vs en 0.600、zh mrr 0.333 vs en 0.730（数字见 BENCHMARK_CARD §6）——中文跨语言检索弱于英文，真实 bge-m3 未跑，结论待真实模型链路验证 |

---

## 11. 未实现 / 待产品决策汇总

| 项 | 状态 | 原因 / 决策点 |
|----|------|--------------|
| 认证体系（OIDC/SSO） | ⬜❓ | 身份依赖可信反向代理注入；生产认证方案需产品决策（企业 IdP 对接） |
| 低证据阈值提示 | ⬜❓ | 证据分数已透传，展示策略需产品决策 |
| 多轮对话 | ⬜❓ | MVP 范围锁定（Spec §3）；v2 候选 |
| 真实模型链路验证 | ⬜ | Docling/bge-m3/reranker/LLM 均 `NOT_RUN`（无密钥、无真实权重环境授权） |
| 自动纠错回路 | ⬜ | 依赖真实链路与运营数据 |
| 版本回滚操作 | ⬜❓ | 归档数据保留，回滚 UI 需产品决策 |
| 评测回归门禁 | ⬜❓ | 历史报告已落库，门禁策略需产品决策 |
| 应用层超时/背压 | ⬜❓ | 目前仅 nginx 长超时兜底 |

## 12. 市场基线对照（厂商数值不可泛化）

> 以下为能力对照，**不引用任何厂商评测数值**——厂商数字来自各自封闭环境/语料，不可跨产品泛化；本表只做能力维度的对标定位。

| 市场基线 | 对标能力 | DocRAG 对应状态 | 差异说明 |
|----------|----------|----------------|----------|
| Google NotebookLM `sources` | 回答锚定原文来源、可跳转核对 | ✅ 引用锚定（页码/bbox）+ 原文预览跳转 | NotebookLM 为托管多源聚合；DocRAG 为本地部署单库，引用粒度到页/bbox |
| Azure AI Search RAG | 检索 + 引用 + 权限（向量/关键词混合） | ✅ 混合检索（FAISS+FTS5+RRF）+ 引用 + 文档级 ACL | Azure 是托管搜索服务；DocRAG 本地零外部依赖，规模上限不同（内存 FAISS） |
| Microsoft Foundry evaluations | 评测/指标体系（含置信区间与分层报告） | 🆕 版本化评测：CI（bootstrap/Wilson）、四维切片、per-query、provenance | 本轮仅无密钥工程基线，真实模型评测 `NOT_RUN` |
| Google data-source ACL | 数据源级权限控制 | 🆕 租户 + 属主/组/管理员 ACL，fail-closed | 身份注入依赖可信反向代理；无内置认证（见 §3） |
| Google Document AI OCR | 高精度托管 OCR | ⬜ 深度 OCR 未实现 | Docling OCR extra 路径未验证；评测语料为文本型 PDF，无 OCR 评分 |
| OWASP LLM06:2025（过度代理 Excessive Agency） | 限制 LLM 可执行操作范围 | ✅ 无工具调用面；生成内容缓冲校验（无有效引用不泄出）、零分候选不冒充证据 | 本应用模型只读上下文 + 生成文本，攻击面小；引用/弃答机制为输出侧护栏 |
| WCAG（可达性） | 键盘可达、语义化、动效降级 | ✅ 基础：Radix 无障碍原语、`prefers-reduced-motion`、`aria-label` | 无自动化 a11y 测试（⬜）；未做完整 WCAG 2.1 AA 审计（❓ 需要产品决策是否纳入验收） |
