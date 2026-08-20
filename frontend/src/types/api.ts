// =============================================================================
// API 契约类型（依据 SPEC.md §5 / §6 + 成熟度契约，前后端共享的唯一依据）
// 所有端点前缀 /api/v1。
// 注意：后端契约字段以「可选」方式声明，字段缺失时前端必须容错。
// =============================================================================

export type DocStatus =
  | 'queued'
  | 'parsing'
  | 'chunking'
  | 'embedding'
  | 'indexed'
  | 'warning'
  | 'failed'
  | 'cancelled';

export interface DocumentItem {
  id: string;
  filename: string;
  sha256?: string | null;
  page_count: number | null;
  chunk_count: number | null;
  status: DocStatus;
  error: string | null;
  created_at?: string | null; // ISO 8601
  updated_at?: string;
  /** 来源版本号（上传替换版本后 +1），缺失容错 */
  version?: number;
  /** 来源 ID（同一来源的多版本共享），缺失容错 */
  source_id?: string;
  /** 是否当前生效版本，缺失时视为 true */
  is_active?: boolean;
}

export interface ChunkPreview {
  id: number;
  seq: number;
  page_no: number;
  section: string | null;
  content: string;
  bbox: Bbox | null;
}

export interface DocumentDetail extends DocumentItem {
  chunks: ChunkPreview[];
}

/** Docling 归一化坐标（left/top/right/bottom，0–1） */
export interface Bbox {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

export interface UploadResponse {
  document_id: string;
  status: DocStatus;
}

// ---- 健康 / 后端状态（与 backend routes/meta.py 实际返回对齐）----
export interface ModelHealth {
  backend?: string;
  status?: string; // 'ready' | 'loading' | ...
}

export interface HealthResponse {
  status?: string; // 'ok' | 'degraded' | ...
  db?: boolean;
  models?: {
    embed?: ModelHealth;
    rerank?: ModelHealth;
    llm?: ModelHealth;
  };
}

export interface BackendItem {
  backend?: string;
  ready?: boolean;
  detail?: string;
}

export interface BackendStatus {
  llm: BackendItem;
  rerank: BackendItem;
  embedding: BackendItem;
}

/** F6 溯源契约：page 必带，bbox 可选（归一化 0–1）。新契约字段 sourceId/version/title/createdAt 可空容错。 */
export interface Citation {
  index: number;
  docId: string;
  docName: string;
  page: number;
  bbox?: Bbox;
  snippet?: string;
  sourceId?: string;
  title?: string | null;
  version?: number | string | null;
  createdAt?: string | null;
}

export interface ChatRequest {
  query: string;
  document_ids?: string[];
  rerank?: boolean;
}

// ---- SSE 事件载荷（全字段可选：后端字段缺失/为 null 时前端容错）----
export interface StagePayload {
  stage?: string | null;
}

export interface DeltaPayload {
  text?: string;
}

export interface CitationPayload {
  index?: number;
  docId?: string;
  docName?: string;
  page?: number | null;
  bbox?: Bbox | null;
  snippet?: string | null;
  // 成熟度契约字段
  sourceId?: string;
  title?: string | null;
  version?: number | string | null;
  createdAt?: string | null;
}

export interface EvidenceCandidate {
  sourceId?: string | null;
  title?: string | null;
  version?: number | string | null;
  page?: number | null;
  snippet?: string | null;
}

export interface NoAnswerPayload {
  reason?: string | null;
  evidence?: EvidenceCandidate[] | null;
}

export interface DonePayload {
  trace_id?: string | null;
  selected_document_ids?: string[] | null;
}

export interface ErrorPayload {
  message?: string;
  trace_id?: string;
}

// ---- 反馈 ----
export type FeedbackIssueType =
  | 'wrong_source'
  | 'unsupported'
  | 'stale'
  | 'missing'
  | 'bad_answer';

export interface FeedbackRequest {
  trace_id?: string;
  useful: boolean;
  issue_type?: FeedbackIssueType | null;
  comment?: string;
}

// ---- 文档 ACL（来源访问控制）----
export interface DocumentAcl {
  tenant_id: string;
  owner_user_id: string;
  groups: string[];
}

// ---- 评测 ----
// 与后端 schemas.EvaluationReport 对齐（metrics 中 recall_at_k / hit_rate_at_k 为按 K 分组的字典）
export interface EvaluationMetrics {
  citation_accuracy: number; // 0–1，引用页码命中率
  recall_at_k: Record<number, number>; // { 5: x, 10: y }
  hit_rate_at_k: Record<number, number>; // { 5: x, 10: y }
  mrr: number; // 0–1（Mean Reciprocal Rank）
  num_queries: number;
  embedding_backend?: string;
  /** 置信区间（如有）：metric -> [low, high] 或 {low, high} */
  ci?: Record<string, unknown>;
  /** 适配器链路状态（VERIFIED/NOT_RUN）；public_nist 报告将其内嵌于 metrics */
  provenance?: string | Record<string, string>;
  profile?: string;
}

export interface EvaluationPerQuery {
  id: string;
  query: string;
  expected_pages: number[];
  gold_pages?: number[]; // 容错：后端可能用 gold_pages 命名
  retrieved_pages: number[];
  citations?: Array<{ page?: number | null; source?: string | null; title?: string | null } | string>;
  answer?: string;
  observed_answer?: string; // 容错：observed 优先
  hit: boolean;
  provenance?: string; // 'VERIFIED' | 'NOT_RUN' | ...
}

export interface EvaluationReport {
  metrics: EvaluationMetrics;
  per_query: EvaluationPerQuery[];
  config: Record<string, unknown>;
  /** 链路验证状态：单字符串或 {component: 'VERIFIED'|'NOT_RUN'} 映射 */
  provenance?: string | Record<string, string>;
}

export interface EvaluationRunConfig {
  profile?: 'public_nist' | 'synthetic_smoke';
  dataset?: string;
}

// ---- 运行时配置（设置页）----
export type AcceleratorMode = 'auto' | 'cuda' | 'cpu';

export type EmbedBackend = 'bge-m3' | 'mock';
export type RerankBackend = 'bge-reranker-v2-m3' | 'mock';
export type ParseBackend = 'docling' | 'mock';

export interface RuntimeLlmConfig {
  backend: 'mock' | 'ollama' | 'openai';
  base_url: string;
  model: string;
  api_key_set: boolean;
}

export interface RuntimeEmbedConfig {
  backend: EmbedBackend;
  model: string; // 模型名（HF id 或本地路径）
}

export interface RuntimeRerankConfig {
  backend: RerankBackend;
  model: string;
}

export interface RuntimeParseConfig {
  backend: ParseBackend;
}

export interface RuntimeConfigResponse {
  llm: RuntimeLlmConfig;
  embed: RuntimeEmbedConfig;
  rerank: RuntimeRerankConfig;
  parse: RuntimeParseConfig;
  apply_mode: 'runtime_override';
  /** 计算加速档位（auto/cuda/cpu），缺失容错 */
  accelerator?: AcceleratorMode;
  /** 当前生效设备（'cuda' | 'cpu'），缺失容错 */
  device?: string;
  cuda_available?: boolean;
}

export interface SettingsUpdatePayload {
  llm?: {
    /** 空字符串 = 清除覆盖，回落环境变量默认 */
    backend?: 'mock' | 'ollama' | 'openai' | '';
    base_url?: string;
    api_key?: string;
    model?: string;
    /** 空字符串 = 清除覆盖，回落 env 的 RAG_ACCELERATOR */
    accelerator?: AcceleratorMode | '';
  };
  /** 仅传要改的字段；空字符串清除覆盖回落 env */
  embed?: {
    backend?: EmbedBackend | '';
    model?: string;
  };
  rerank?: {
    backend?: RerankBackend | '';
    model?: string;
  };
  parse?: {
    backend?: ParseBackend | '';
  };
}
