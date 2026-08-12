import { Cpu, Info } from 'lucide-react';
import { useBackends } from '@/hooks/useSystem';
import { Toggle } from '@/components/ui/Switch';
import { Tooltip } from '@/components/ui/Tooltip';
import { cn } from '@/lib/cn';

// 双后端选择器（顶部常驻）：LLM 后端 / 模型名展示 + Rerank 开关。
// 实际操作靠后端 env，前端仅展示 + 提示用户改 env（MVP 不接设置写回）。
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
        <span className="text-muted">LLM 后端</span>
        <span className="rounded-sm bg-surface-2 px-2 py-0.5 font-mono text-xs text-fg">
          {isLoading ? '…' : backend}
        </span>
        <Tooltip content="到「设置」页可运行时配置模型 API（后端/Base URL/模型/Key），无需改环境变量">
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
