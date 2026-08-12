import { useState } from 'react';
import { Send, ThumbsDown, ThumbsUp } from 'lucide-react';
import { submitFeedback } from '@/api/feedback';
import { extractErrorMessage } from '@/api/client';
import type { FeedbackIssueType } from '@/types/api';
import type { ChatMessage } from '@/types/chat';
import { Button } from '@/components/ui/Button';
import { Textarea } from '@/components/ui/Input';
import { cn } from '@/lib/cn';

const ISSUE_TYPES: { id: FeedbackIssueType; label: string }[] = [
  { id: 'wrong_source', label: '来源错误' },
  { id: 'unsupported', label: '回答无依据' },
  { id: 'stale', label: '信息过时' },
  { id: 'missing', label: '信息缺失' },
  { id: 'bad_answer', label: '回答质量差' },
];

/** 答案反馈：有用 / 没用（+ issue_type + 可选 comment），POST /api/v1/feedback */
export function FeedbackPanel({ message }: { message: ChatMessage }) {
  const [useful, setUseful] = useState<boolean | null>(null);
  const [issueType, setIssueType] = useState<FeedbackIssueType | null>(null);
  const [comment, setComment] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!message.traceId) {
    return <span className="text-xs text-meta">（该回答无 trace 记录，无法提交反馈）</span>;
  }
  if (submitted) {
    return <span className="text-xs text-success">已收到反馈，谢谢</span>;
  }

  const submit = async () => {
    if (useful == null) return;
    setSubmitting(true);
    setError(null);
    try {
      await submitFeedback({
        trace_id: message.traceId,
        useful,
        issue_type: useful ? null : issueType,
        comment: comment.trim() || undefined,
      });
      setSubmitted(true);
    } catch (e) {
      setError(extractErrorMessage(e, '反馈提交失败'));
    } finally {
      setSubmitting(false);
    }
  };

  const verdictBtn = (value: boolean) => (
    <button
      type="button"
      onClick={() => setUseful(value)}
      aria-pressed={useful === value}
      className={cn(
        'inline-flex items-center gap-1 rounded-sm border px-2 py-1 text-xs transition-colors focus-visible:outline-none',
        useful === value
          ? value
            ? 'border-success/50 text-success'
            : 'border-danger/50 text-danger'
          : 'border-line text-muted hover:bg-surface-2 hover:text-fg',
      )}
    >
      {value ? <ThumbsUp size={12} aria-hidden /> : <ThumbsDown size={12} aria-hidden />}
      {value ? '有用' : '没用'}
    </button>
  );

  return (
    <div className="flex min-w-0 flex-wrap items-center gap-2">
      <span className="text-xs text-meta">这个回答有帮助吗？</span>
      {verdictBtn(true)}
      {verdictBtn(false)}
      {useful != null && (
        <Button
          size="sm"
          variant={useful ? 'secondary' : 'primary'}
          loading={submitting}
          onClick={submit}
          leadingIcon={<Send size={12} />}
        >
          提交
        </Button>
      )}
      {useful === false && (
        <div className="flex w-full flex-wrap items-center gap-2">
          {ISSUE_TYPES.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setIssueType(t.id)}
              aria-pressed={issueType === t.id}
              className={cn(
                'rounded-pill border px-2 py-0.5 text-xs transition-colors focus-visible:outline-none',
                issueType === t.id
                  ? 'border-accent text-accent'
                  : 'border-line text-meta hover:bg-surface-2',
              )}
            >
              {t.label}
            </button>
          ))}
          <Textarea
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={1}
            placeholder="补充说明（可选）"
            className="min-h-0 max-w-xs py-1 text-xs"
          />
        </div>
      )}
      {error && <span className="text-xs text-danger">{error}</span>}
    </div>
  );
}
