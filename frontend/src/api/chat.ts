import type {
  ChatRequest,
  Citation,
  CitationPayload,
  DeltaPayload,
  DonePayload,
  ErrorPayload,
  NoAnswerPayload,
  StagePayload,
} from '@/types/api';
import type { ChatStage, NoAnswerInfo } from '@/types/chat';

// =============================================================================
// /chat SSE 流式问答解析（成熟度契约）
// 事件协议：
//   event: stage    -> { stage: 'retrieving'|'reranking'|'generating' }
//   event: delta    -> { text }
//   event: citation -> { sourceId?, version?, title?, createdAt?, page?, snippet?, index?, ... }
//   event: no_answer-> { reason?, evidence? }
//   event: done     -> { trace_id?, selected_document_ids? }
//   event: error    -> { message? }
// 所有载荷字段均可缺省 / 为 null，解析端容错归一化。
// =============================================================================

export interface ChatStreamHandlers {
  onStage: (stage: ChatStage) => void;
  onDelta: (text: string) => void;
  onCitation: (citation: Citation) => void;
  /** 已归一化（null -> undefined / []），可直接存入 ChatMessage.noAnswer */
  onNoAnswer: (payload: NoAnswerInfo) => void;
  onDone: (payload: DonePayload) => void;
  onError: (message: string) => void;
}

interface ParsedSse {
  event: string;
  data: string;
}

function parseMessage(raw: string): ParsedSse | null {
  let event = 'message';
  const dataLines: string[] = [];
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataLines.push(line.slice(5).trim());
  }
  const data = dataLines.join('\n');
  if (!data) return null;
  return { event, data };
}

function safeJson<T>(data: string): T | null {
  try {
    return JSON.parse(data) as T;
  } catch {
    return null;
  }
}

/** 归一化 citation 载荷：兼容新旧两代契约（index/docId/docName 旧字段 + sourceId/title/version 新字段） */
function normalizeCitation(raw: CitationPayload, fallbackIndex: number): Citation {
  const page = typeof raw.page === 'number' && raw.page > 0 ? raw.page : 1;
  // docId 优先：docId 是版本行 id（始终可加载的文件），sourceId 是跨版本稳定 id
  // （引用替换版本后 sourceId 指向已归档版本，用它加载 PDF 会取到旧文件）
  const docId = raw.docId ?? raw.sourceId ?? '';
  const sourceId = raw.sourceId ?? docId;
  const docName = raw.title ?? raw.docName ?? '';
  const bbox =
    raw.bbox && typeof raw.bbox.left === 'number' && typeof raw.bbox.top === 'number'
      ? raw.bbox
      : undefined;
  return {
    index: typeof raw.index === 'number' ? raw.index : fallbackIndex,
    docId,
    docName: docName || '未知文档',
    page,
    bbox,
    snippet: typeof raw.snippet === 'string' ? raw.snippet : undefined,
    sourceId: sourceId || undefined,
    title: typeof raw.title === 'string' ? raw.title : undefined,
    version: typeof raw.version === 'number' || typeof raw.version === 'string' ? raw.version : undefined,
    createdAt: typeof raw.createdAt === 'string' ? raw.createdAt : undefined,
    rrfScore: typeof raw.rrfScore === 'number' ? raw.rrfScore : undefined,
    faissScore: raw.faissScore ?? undefined,
    ftsScore: raw.ftsScore ?? undefined,
  };
}

export async function streamChat(
  req: ChatRequest,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<void> {
  let res: Response;
  try {
    res = await fetch('/api/v1/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(req),
      signal,
    });
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') return;
    handlers.onError('无法连接问答服务，请确认后端已启动');
    return;
  }

  if (!res.ok || !res.body) {
    let msg = '问答服务不可用';
    try {
      const b = (await res.json()) as ErrorPayload;
      if (b?.message) msg = b.message;
    } catch {
      /* ignore */
    }
    handlers.onError(msg);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let finished = false;
  let citationIndex = 1;

  const dispatch = (parsed: ParsedSse) => {
    switch (parsed.event) {
      case 'stage': {
        const p = safeJson<StagePayload>(parsed.data);
        const s = p?.stage;
        if (s === 'retrieving' || s === 'reranking' || s === 'generating') {
          handlers.onStage(s as ChatStage);
        }
        break;
      }
      case 'delta': {
        const p = safeJson<DeltaPayload>(parsed.data);
        handlers.onDelta(p?.text ?? parsed.data);
        break;
      }
      case 'citation': {
        const p = safeJson<CitationPayload>(parsed.data);
        if (p) handlers.onCitation(normalizeCitation(p, citationIndex++));
        break;
      }
      case 'no_answer': {
        const p = safeJson<NoAnswerPayload>(parsed.data);
        if (p) {
          handlers.onNoAnswer({
            reason: typeof p.reason === 'string' ? p.reason : undefined,
            evidence: Array.isArray(p.evidence) ? p.evidence : [],
          });
        }
        break;
      }
      case 'error': {
        const p = safeJson<ErrorPayload>(parsed.data);
        handlers.onError(p?.message ?? '问答过程中发生错误');
        finished = true;
        break;
      }
      case 'done': {
        const p = safeJson<DonePayload>(parsed.data) ?? {};
        finished = true;
        handlers.onDone({
          trace_id: typeof p.trace_id === 'string' ? p.trace_id : undefined,
          selected_document_ids: Array.isArray(p.selected_document_ids) ? p.selected_document_ids : [],
        });
        break;
      }
      default:
        break;
    }
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx: number;
      while ((idx = buffer.indexOf('\n\n')) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const parsed = parseMessage(raw);
        if (parsed) dispatch(parsed);
      }
    }
    // 处理结尾可能缺少尾部空行的残帧
    if (buffer.trim()) {
      const parsed = parseMessage(buffer);
      if (parsed) dispatch(parsed);
    }
  } catch (err) {
    if ((err as Error)?.name === 'AbortError') return;
    handlers.onError('问答流读取中断');
    return;
  }

  if (!finished) handlers.onDone({});
}
