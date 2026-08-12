import { AlertCircle, Download } from 'lucide-react';
import type { Citation } from '@/types/api';
import type { ChatMessage } from '@/types/chat';
import { citationLabel, parseCitations } from '@/lib/citation';
import { downloadAnswerExport } from '@/lib/export';
import { usePdfNav } from '@/lib/stores';
import { CitationChip } from './CitationChip';
import { StageIndicator } from './StageIndicator';
import { NoAnswerCard } from './NoAnswerCard';
import { FeedbackPanel } from './FeedbackPanel';
import { Button } from '@/components/ui/Button';
import { cn } from '@/lib/cn';

export function MessageBubble({ message }: { message: ChatMessage }) {
  const goTo = usePdfNav((s) => s.goTo);
  const isUser = message.role === 'user';
  const citationsByIndex = new Map((message.citations ?? []).map((c) => [c.index, c]));
  const segments = !isUser && message.content ? parseCitations(message.content) : null;
  const completed = !isUser && !message.streaming && !message.error;
  const showFooter =
    completed && (message.content.length > 0 || !!message.noAnswer || message.stopped);

  return (
    <div className={cn('flex w-full', isUser ? 'justify-end' : 'justify-start')}>
      <div
        className={cn(
          'max-w-[82%] rounded-md px-4 py-3 text-sm leading-body',
          isUser ? 'bg-surface-2 text-fg' : 'border border-line bg-surface text-fg',
          message.error && 'border-danger',
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap break-words">{message.content}</p>
        ) : message.error ? (
          <div className="flex items-start gap-2 text-danger">
            <AlertCircle size={16} className="mt-0.5 shrink-0" />
            <p>{message.error}</p>
          </div>
        ) : (
          <div className="space-y-2">
            {message.stage && <StageIndicator stage={message.stage} />}
            <p className="whitespace-pre-wrap break-words">
              {segments?.map((seg, i) =>
                seg.kind === 'text' ? (
                  <span key={i}>{seg.text}</span>
                ) : (
                  <CitationChip
                    key={i}
                    citation={
                      citationsByIndex.get(seg.index) ?? {
                        index: seg.index,
                        docId: '',
                        docName: '未知文档',
                        page: 1,
                      }
                    }
                  />
                ),
              )}
              {message.streaming && (
                <span className="ml-0.5 inline-block h-4 w-[3px] translate-y-[2px] animate-[blink-caret_1s_infinite] bg-accent align-middle" />
              )}
            </p>
            {message.stopped && !message.streaming && (
              <p className="text-xs text-meta">已停止生成（已生成内容与引用保留）</p>
            )}
            {message.noAnswer && !message.streaming && <NoAnswerCard info={message.noAnswer} />}
            {message.citations && message.citations.length > 0 && !message.streaming && (
              <CitationList
                citations={message.citations}
                onJump={(c) =>
                  goTo({ page: c.page, bbox: c.bbox, index: c.index, docId: c.docId })
                }
              />
            )}
            {showFooter && (
              <div className="flex flex-wrap items-center gap-3 border-t border-line-soft pt-2">
                <FeedbackPanel message={message} />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => downloadAnswerExport(message)}
                  leadingIcon={<Download size={12} />}
                >
                  导出 JSON
                </Button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function CitationList({
  citations,
  onJump,
}: {
  citations: Citation[];
  onJump: (c: Citation) => void;
}) {
  return (
    <div className="mt-1 border-t border-line-soft pt-2">
      <p className="mb-1 text-xs text-meta caps-label">引用溯源</p>
      <ul className="space-y-1">
        {citations.map((c) => (
          <li key={c.index}>
            <button
              type="button"
              onClick={() => onJump(c)}
              className="flex w-full items-center gap-2 rounded-sm px-2 py-1 text-left text-xs text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none"
            >
              <span className="flex h-4 min-w-4 shrink-0 items-center justify-center rounded-sm border border-citation bg-citation-bg px-1 font-mono text-[10px] text-citation">
                {c.index}
              </span>
              <span className="truncate text-fg">{citationLabel(c)}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
