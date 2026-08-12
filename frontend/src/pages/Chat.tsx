import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { MessageSquare, Send, Square } from 'lucide-react';
import { streamChat } from '@/api/chat';
import { useDocuments } from '@/hooks/useDocuments';
import { addRecentQuery } from '@/lib/recentQueries';
import type { ChatMessage, SourceManifest } from '@/types/chat';
import { MessageBubble } from '@/components/common/MessageBubble';
import { PDFPreview } from '@/components/common/PDFPreview';
import { ScopePanel } from '@/components/common/ScopePanel';
import { BackendSelector } from '@/components/common/BackendSelector';
import { Button } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Input';
import { EmptyState } from '@/components/ui/EmptyState';

export function Chat() {
  const [params] = useSearchParams();
  const initialQuery = useRef(params.get('q') ?? '');
  const initialDoc = useRef(params.get('doc') ?? '');

  const [input, setInput] = useState(initialQuery.current);
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [previewDocId, setPreviewDocId] = useState<string | null>(null);
  const [rerank, setRerank] = useState(true);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const initRef = useRef(false);

  const { data: docs = [], isLoading: docsLoading } = useDocuments();

  // 仅 indexed + active 的文档可加入问答范围
  const selectable = useMemo(
    () => docs.filter((d) => d.status === 'indexed' && d.is_active !== false),
    [docs],
  );
  const selectableIds = useMemo(() => new Set(selectable.map((d) => d.id)), [selectable]);

  // ?doc= 参数：文档就绪后预选并预览
  useEffect(() => {
    if (initRef.current || selectable.length === 0) return;
    initRef.current = true;
    if (initialDoc.current && selectableIds.has(initialDoc.current)) {
      setSelectedIds([initialDoc.current]);
      setPreviewDocId(initialDoc.current);
    }
  }, [selectable, selectableIds]);

  const updateLastAssistant = useCallback((updater: (m: ChatMessage) => ChatMessage) => {
    setMessages((prev) => {
      const idx = prev.length - 1;
      if (idx < 0 || prev[idx]?.role !== 'assistant') return prev;
      const copy = prev.slice();
      copy[idx] = updater(copy[idx]);
      return copy;
    });
  }, []);

  const send = useCallback(
    (raw: string) => {
      const query = raw.trim();
      if (!query || isStreaming || selectable.length === 0) return;
      addRecentQuery(query);

      // 提问时刻保存不可变 source manifest（供导出）
      const scopeIds = selectedIds.filter((id) => selectableIds.has(id));
      const manifestDocs = (scopeIds.length
        ? docs.filter((d) => scopeIds.includes(d.id))
        : selectable
      ).map((d) => ({
        id: d.id,
        filename: d.filename,
        version: d.version,
        sha256: d.sha256 ?? null,
        page_count: d.page_count ?? null,
      }));
      const sourceManifest: SourceManifest = { scope_ids: scopeIds, documents: manifestDocs };
      const now = new Date().toISOString();

      const userMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'user',
        content: query,
        createdAt: now,
      };
      const aiMsg: ChatMessage = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        citations: [],
        streaming: true,
        stage: null,
        noAnswer: null,
        query,
        createdAt: now,
        sourceManifest,
      };
      setMessages((prev) => [...prev, userMsg, aiMsg]);
      setIsStreaming(true);

      const controller = new AbortController();
      controllerRef.current = controller;
      streamChat(
        { query, document_ids: scopeIds.length ? scopeIds : undefined, rerank },
        {
          onStage: (stage) => updateLastAssistant((m) => ({ ...m, stage })),
          onDelta: (text) => updateLastAssistant((m) => ({ ...m, content: m.content + text })),
          onCitation: (c) =>
            updateLastAssistant((m) => ({ ...m, citations: [...(m.citations ?? []), c] })),
          onNoAnswer: (p) => updateLastAssistant((m) => ({ ...m, noAnswer: p })),
          onDone: (p) =>
            updateLastAssistant((m) => ({
              ...m,
              streaming: false,
              stage: null,
              traceId: p.trace_id ?? undefined,
              selectedDocumentIds: p.selected_document_ids ?? [],
            })),
          onError: (message) =>
            updateLastAssistant((m) => ({
              ...m,
              streaming: false,
              stage: null,
              error: message,
            })),
        },
        controller.signal,
      ).finally(() => {
        setIsStreaming(false);
        controllerRef.current = null;
      });
    },
    [isStreaming, selectedIds, selectableIds, selectable, docs, rerank, updateLastAssistant],
  );

  const stop = useCallback(() => {
    controllerRef.current?.abort();
    updateLastAssistant((m) =>
      m.streaming ? { ...m, streaming: false, stopped: true, stage: null } : m,
    );
    setIsStreaming(false);
  }, [updateLastAssistant]);

  // 卸载时中止未完成的流
  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  // 新消息自动滚到底部
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const canSend = selectable.length > 0;
  const pendingDocs = docs.length - selectable.length;

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 px-4 pt-4 md:px-6">
        <BackendSelector rerank={rerank} onRerankChange={setRerank} />
      </div>

      <div className="flex min-h-0 flex-1">
        <ScopePanel
          docsLoading={docsLoading}
          selectable={selectable}
          selectedIds={selectedIds}
          previewDocId={previewDocId}
          pendingDocs={pendingDocs}
          onToggle={(id, checked) =>
            setSelectedIds((prev) => (checked ? [...prev, id] : prev.filter((x) => x !== id)))
          }
          onPreview={setPreviewDocId}
          onClear={() => setSelectedIds([])}
        />

        {/* 中：对话 */}
        <section className="flex min-w-0 flex-1 flex-col">
          <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4 md:px-6">
            {messages.length === 0 ? (
              <div className="flex h-full items-center justify-center">
                <EmptyState
                  icon={MessageSquare}
                  title="开始你的第一次溯源问答"
                  description="在左侧勾选文档可限定范围；直接提问将检索全部已索引文档。回答中的 [n] 角标可点击跳转至 PDF 原文对应段落。"
                />
              </div>
            ) : (
              messages.map((m) => <MessageBubble key={m.id} message={m} />)
            )}
          </div>
          <div className="shrink-0 border-t border-line p-3">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                send(input);
              }}
              className="mx-auto flex max-w-3xl items-end gap-2"
            >
              <Textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    send(input);
                  }
                }}
                rows={1}
                disabled={!canSend}
                placeholder={
                  canSend
                    ? '就选中的文档提问，或留空检索全部文档…'
                    : '知识库为空：请先上传 PDF 并等待索引完成'
                }
                className="max-h-32 min-h-[40px] flex-1"
              />
              {isStreaming ? (
                <Button type="button" variant="secondary" onClick={stop} leadingIcon={<Square size={14} />}>
                  停止
                </Button>
              ) : (
                <Button
                  type="submit"
                  disabled={!input.trim() || !canSend}
                  leadingIcon={<Send size={16} />}
                >
                  发送
                </Button>
              )}
            </form>
            {!canSend && (
              <p className="mx-auto mt-1.5 max-w-3xl text-xs text-warn">
                知识库为空：上传 PDF 并在「文档库」页等待状态变为「已索引」后即可提问。
              </p>
            )}
          </div>
        </section>

        {/* 右：PDF 预览 + 引用高亮（跨文档引用由 onNavigateDoc 切换） */}
        <aside className="hidden w-[42%] max-w-xl shrink-0 flex-col border-l border-line lg:flex">
          <PDFPreview docId={previewDocId} onNavigateDoc={(id) => setPreviewDocId(id)} />
        </aside>
      </div>
    </div>
  );
}
