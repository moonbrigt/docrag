import { Cpu, Info } from 'lucide-react';
import { useBackends } from '@/hooks/useSystem';
import { Toggle } from '@/components/ui/Switch';
import { Tooltip } from '@/components/ui/Tooltip';
import { cn } from '@/lib/cn';

// 顶部常驻状态条：展示当前对话后端与模型 + Rerank 开关。
// 后端/模型/地址在「设置」页运行时配置并写回，此条仅展示。
const BACKEND_LABEL: Record<string, string> = {
  ollama: 'Ollama',
  openai: 'OpenAI 兼容',
  mock: '未配置',
};
export function BackendSelector({
  rerank,
  onRerankChange,
}: {
  rerank: boolean;
  onRerankChange: (value: boolean) => void;
}) {
  const { data, isLoading } = useBackends();
  const backend = data?.llm.backend ?? 'ollama';
  const detail = data?.llm.detail ?? '（未配置）';

  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-md border border-line bg-surface px-3 py-2 text-sm">
      <div className="flex items-center gap-2">
        <Cpu size={16} className="text-meta" />
        <span className="text-muted">对话后端</span>
        <span className="rounded-sm bg-surface-2 px-2 py-0.5 font-mono text-xs text-fg">
          {isLoading ? '…' : BACKEND_LABEL[backend] ?? backend}
        </span>
        <Tooltip content="到「设置」页可运行时配置对话模型与向量嵌入接口，无需改环境变量">
          <Info size={14} className="text-meta" />
        </Tooltip>
      </div>
      <div className="flex min-w-0 items-center gap-2">
        <span className="text-muted">状态</span>
        <span className="truncate font-mono text-xs text-fg">{isLoading ? '…' : detail}</span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-muted">Rerank</span>
        <Toggle checked={rerank} onCheckedChange={onRerankChange} aria-label="启用 Rerank 重排" />
        <span className={cn('text-xs', rerank ? 'text-success' : 'text-meta')}>
          {rerank ? '已开启' : '已关闭'}
        </span>
      </div>
    </div>
  );
}
