import type { LucideIcon } from 'lucide-react';
import { Circle, Cpu, Database, FileText } from 'lucide-react';
import type { DocumentItem } from '@/types/api';
import { useHealth } from '@/hooks/useSystem';
import { formatCount } from '@/lib/format';
import { cn } from '@/lib/cn';

type Tone = 'neutral' | 'success' | 'warn' | 'danger' | 'accent';

export function SystemStatus({ documents }: { documents: DocumentItem[] }) {
  const health = useHealth();
  const total = documents.length;
  const processing = documents.filter((d) =>
    ['queued', 'parsing', 'chunking', 'embedding'].includes(d.status),
  ).length;
  const chunks = documents.reduce((s, d) => s + (d.chunk_count ?? 0), 0);
  const dbOk = health.data?.db ?? false;
  const embed = health.data?.models?.embed;
  const embedReady = embed?.status === 'ready';
  const embedLoading = embed?.status === 'loading';

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      <Stat icon={FileText} label="文档" value={formatCount(total)} tone="accent" />
      <Stat icon={Database} label="分块" value={formatCount(chunks)} tone="accent" />
      <Stat
        icon={Circle}
        label="解析中"
        value={formatCount(processing)}
        tone={processing > 0 ? 'warn' : 'neutral'}
      />
      <Stat icon={Database} label="向量库" value={dbOk ? '正常' : '异常'} tone={dbOk ? 'success' : 'danger'} />
      <Stat
        icon={Cpu}
        label="Embedding"
        value={
          health.isLoading ? '…' : embedReady ? '就绪' : embedLoading ? '加载中' : '未连接'
        }
        tone={embedReady ? 'success' : 'warn'}
      />
    </div>
  );
}

function Stat({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: LucideIcon;
  label: string;
  value: string;
  tone: Tone;
}) {
  const dot: Record<Tone, string> = {
    neutral: 'bg-meta',
    success: 'bg-success',
    warn: 'bg-warn',
    danger: 'bg-danger',
    accent: 'bg-accent',
  };
  return (
    <div className="rounded-md border border-line bg-surface px-3 py-3">
      <div className="flex items-center gap-2 text-xs text-meta">
        <Icon size={14} />
        <span>{label}</span>
        <span className={cn('ml-auto h-1.5 w-1.5 rounded-pill', dot[tone])} />
      </div>
      <p className="mt-1 font-mono text-md text-fg">{value}</p>
    </div>
  );
}
