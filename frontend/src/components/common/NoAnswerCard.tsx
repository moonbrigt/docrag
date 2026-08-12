import { SearchX } from 'lucide-react';
import type { NoAnswerInfo } from '@/types/chat';

// 「无答案」状态卡片：展示拒答原因 + 证据候选摘要（未达引用阈值的候选来源）。
export function NoAnswerCard({ info }: { info: NoAnswerInfo }) {
  const evidence = info.evidence ?? [];
  return (
    <div className="rounded-md border border-warn/40 bg-warn/5 p-3">
      <div className="flex items-center gap-2">
        <SearchX size={16} className="shrink-0 text-warn" aria-hidden />
        <span className="text-sm font-emphasize text-fg">未找到可支撑的答案</span>
      </div>
      {info.reason && <p className="mt-1 text-xs text-muted">{info.reason}</p>}
      {evidence.length > 0 && (
        <div className="mt-2 border-t border-line-soft pt-2">
          <p className="text-xs caps-label text-meta">相关证据候选</p>
          <ul className="mt-1 space-y-1">
            {evidence.map((e, i) => (
              <li key={i} className="text-xs text-muted">
                <span className="text-fg">{e.title || e.sourceId || '未知来源'}</span>
                {e.version != null && e.version !== '' && <span> · v{e.version}</span>}
                {e.page != null && e.page > 0 && <span> · p.{e.page}</span>}
                {e.snippet && <span className="block truncate">{e.snippet}</span>}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
