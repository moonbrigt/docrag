# Changelog

本项目采用 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/) 风格。版本号遵循语义化版本（未发布 1.0 前以 0.x 递增）。

## [Unreleased]

### 2026-08-12 成熟度扩展（尚未发布，全部改动见 git diff）

#### 新增

- **公开评测集 `public_nist`**：2 份 NIST 报告 PDF（SHA-256 校验、DOI、NIST Open License）+ 18 题页码/证据 gold（16 可答 + 2 不可答，含中文跨语言题与 hard-negative）；`public_dataset / baselines / eval_metrics / public_runner` 模块，bootstrap/Wilson 95% CI、四维切片、确定性自检；`/api/v1/evaluation/run` 默认该 profile（未 prepare 返回 409）
- **检索消融对比**（`app/evaluation/ablation.py`）：BM25 / mock 稠密 / RRF 混合 / 混合+重排四路变体，报告 `ablation` 段 + 前端评测页对比表
- **ACL 与租户隔离**：`Principal(tenant/user/groups)` + 两级权限 fail-closed；可信反向代理身份注入（`RAG_TRUSTED_PROXY`）
- **文档生命周期**：source_id + version + is_active；`cancel / retry / versions` 端点；8 态状态机（warning/cancelled）与事件审计表；重启恢复瞬态任务
- **无答案与证据门**：`no_answer`（no_evidence/not_supported）SSE 事件；生成内容缓冲校验引用，无有效引用不泄出
- **反馈与追踪**：`POST /feedback`、`GET /trace/{id}`；query 原文不落库
- **运行时模型配置**：`GET/PUT /config/settings` + 前端设置页（/settings），改模型 API 无需重启/重建镜像
- **成熟度文档**：MATURITY_MATRIX / DATA_CARD / BENCHMARK_CARD / EVALUATION_PROTOCOL / REPRODUCE / VALIDATION；SECURITY / CONTRIBUTING 说明
- **隔离验收栈**：`docker-compose.acceptance.yml`（project `docrag-acceptance`，端口 3302，独立卷）+ `scripts/docker/manage.sh` 一键管理

#### 修复

- FAISS 检索范围泄漏（`document_ids` 未过滤稠密路）；显式空列表扩张成全库
- 失败摄入的 partial chunks 残留可检索；删除与后台任务孤儿 chunk 竞态
- 无信号检索把零分候选冒充证据；rerank 未就绪时静默降级
- 非属主可读 ACL 主体列表；health/backends 前后端类型漂移
- 旧库升级迁移顺序（`_migrate` 先于 SCHEMA，全新库/旧库双路径回归验证）
- nginx 上传体量上限 1MB（真实 PDF 被拒）；版本替换后引用跳转指向旧文件

#### 已知边界（详见 docs/BENCHMARK_CARD.md 与 VALIDATION.md）

- 真实 Docling / bge-m3 / bge-reranker / LLM 链路 `NOT_RUN`（无权重/密钥授权），mock 不冒充真实模型
- 认证体系为可信代理身份注入，OIDC/SSO 属产品决策；设置页 API Key 明文存本地 SQLite
- 前端无自动化测试（tsc/lint/build 为门禁）；Playwright UI E2E 未实现
