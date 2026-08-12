import { LoaderCircle } from 'lucide-react';
import type { ChatStage } from '@/types/chat';

// 流式问答阶段指示：retrieving / reranking / generating
const LABELS: Record<ChatStage, string> = {
  retrieving: '正在检索相关文档…',
  reranking: '正在重排候选段落…',
  generating: '正在生成回答…',
};

export function StageIndicator({ stage }: { stage: ChatStage | null | undefined }) {
  if (!stage) return null;
  return (
    <div className="flex items-center gap-2 text-xs text-meta">
      <LoaderCircle size={12} className="animate-spin" aria-hidden />
      <span>{LABELS[stage] ?? stage}</span>
    </div>
  );
}
