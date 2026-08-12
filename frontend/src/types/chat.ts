import type { Citation, EvidenceCandidate } from './api';

/** 问答流阶段（stage 事件） */
export type ChatStage = 'retrieving' | 'reranking' | 'generating';

/** no_answer 事件信息：无法回答的原因 + 证据候选摘要 */
export interface NoAnswerInfo {
  reason?: string;
  evidence?: EvidenceCandidate[];
}

/** source manifest 条目（提问时刻不可变快照） */
export interface SourceManifestEntry {
  id: string;
  filename: string;
  version?: number;
  sha256?: string | null;
  page_count?: number | null;
}

/** 提问时保存的来源快照：scope_ids 为用户勾选范围（空 = 全部已索引） */
export interface SourceManifest {
  scope_ids: string[];
  documents: SourceManifestEntry[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
  error?: string;
  streaming?: boolean;
  /** 用户手动中止 SSE 流 */
  stopped?: boolean;
  /** 当前阶段（仅流式期间非空） */
  stage?: ChatStage | null;
  noAnswer?: NoAnswerInfo | null;
  traceId?: string;
  selectedDocumentIds?: string[];
  sourceManifest?: SourceManifest;
  /** assistant 消息上冗余用户问题，供导出与反馈上下文 */
  query?: string;
  createdAt?: string; // ISO 8601
}
