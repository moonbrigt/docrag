import type { ChatMessage, SourceManifestEntry } from '@/types/chat';

// =============================================================================
// 答案导出（本地 JSON，v1）：docrag.answer-export.v1
// 内容：回答 + trace 摘要 + citations + source manifest
// （提问时刻的不可变快照 + done 事件回传的 selected_document_ids）。
// =============================================================================

export interface AnswerExportV1 {
  schema: 'docrag.answer-export.v1';
  exported_at: string; // ISO 8601
  query: string;
  answer: {
    content: string;
    citations: ChatMessage['citations'];
    no_answer: ChatMessage['noAnswer'];
    error: string | null;
    stopped: boolean;
  };
  trace: {
    trace_id: string | null;
    selected_document_ids: string[];
  };
  source_manifest: {
    scope_ids: string[];
    documents: SourceManifestEntry[];
  };
}

export function buildAnswerExport(msg: ChatMessage): AnswerExportV1 {
  return {
    schema: 'docrag.answer-export.v1',
    exported_at: new Date().toISOString(),
    query: msg.query ?? '',
    answer: {
      content: msg.content,
      citations: msg.citations ?? [],
      no_answer: msg.noAnswer ?? null,
      error: msg.error ?? null,
      stopped: !!msg.stopped,
    },
    trace: {
      trace_id: msg.traceId ?? null,
      selected_document_ids: msg.selectedDocumentIds ?? [],
    },
    source_manifest: {
      scope_ids: msg.sourceManifest?.scope_ids ?? [],
      documents: msg.sourceManifest?.documents ?? [],
    },
  };
}

/** 触发浏览器下载导出文件 */
export function downloadAnswerExport(msg: ChatMessage): void {
  const data = buildAnswerExport(msg);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `docrag-answer-${(msg.traceId ?? msg.id).slice(0, 8)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}
