import { Check, LoaderCircle, X } from 'lucide-react';
import type { DocStatus } from '@/types/api';
import { cn } from '@/lib/cn';

// 确定性 5 阶段：上传 → 解析 → 分块 → 嵌入 → 索引（禁用假百分比）
const STAGES = ['上传', '解析', '分块', '嵌入', '索引'];
type StageState = 'pending' | 'active' | 'done' | 'error';

function computeStages(
  status: DocStatus,
  error: string | null,
): { state: StageState; error?: string }[] {
  const done =
    status === 'indexed'
      ? 5
      : status === 'embedding'
        ? 3
        : status === 'chunking'
          ? 2
          : status === 'queued' || status === 'parsing' || status === 'failed'
            ? 1
            : 0;
  const active =
    status === 'parsing' ? 1 : status === 'chunking' ? 2 : status === 'embedding' ? 3 : -1;

  return STAGES.map((_, i) => {
    if (status === 'failed' && i === done) {
      return { state: 'error' as StageState, error: error ?? '处理失败' };
    }
    if (i < done) return { state: 'done' as StageState };
    if (i === active) return { state: 'active' as StageState };
    return { state: 'pending' as StageState };
  });
}

export function Stepper({ status, error }: { status: DocStatus; error?: string | null }) {
  const stages = computeStages(status, error ?? null);

  return (
    <ol className="flex items-center gap-1">
      {stages.map((s, i) => (
        <li key={i} className="flex flex-1 items-center gap-1">
          <div className="flex flex-col items-center gap-1">
            <span
              className={cn(
                'flex h-5 w-5 items-center justify-center rounded-pill border text-[10px]',
                s.state === 'done' && 'border-success bg-success/15 text-success',
                s.state === 'active' && 'border-accent text-accent',
                s.state === 'error' && 'border-danger text-danger',
                s.state === 'pending' && 'border-line text-meta',
              )}
            >
              {s.state === 'done' && <Check size={12} strokeWidth={3} />}
              {s.state === 'active' && <LoaderCircle size={12} className="animate-spin" />}
              {s.state === 'error' && <X size={12} strokeWidth={3} />}
              {s.state === 'pending' && <span className="h-1 w-1 rounded-pill bg-meta" />}
            </span>
            <span
              className={cn(
                'text-[10px]',
                s.state === 'done' && 'text-success',
                s.state === 'active' && 'text-accent',
                s.state === 'error' && 'text-danger',
                s.state === 'pending' && 'text-meta',
              )}
            >
              {STAGES[i]}
            </span>
          </div>
          {i < STAGES.length - 1 && (
            <span
              className={cn(
                'h-px flex-1',
                stages[i].state === 'done' && stages[i + 1].state === 'done' && 'bg-success/40',
                stages[i].state === 'done' && stages[i + 1].state === 'active' && 'bg-accent/50',
                !(
                  (stages[i].state === 'done' && stages[i + 1].state === 'done') ||
                  (stages[i].state === 'done' && stages[i + 1].state === 'active')
                ) && 'bg-line',
              )}
            />
          )}
        </li>
      ))}
    </ol>
  );
}
