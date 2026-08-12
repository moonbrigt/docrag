import type { Citation } from '@/types/api';
import { citationLabel } from '@/lib/citation';
import { usePdfNav } from '@/lib/stores';
import { Tooltip } from '@/components/ui/Tooltip';
import { cn } from '@/lib/cn';

// 引用角标 [n]（F6 灵魂功能）：真实 <button>，可键盘聚焦，hover 提示
// 「来源标题 · v版本 · p.页码」（snippet 一并展示），
// 点击 -> PDF 面板 goToPage（含 bbox，跨文档时由父级切换文档）。
// 反向联动：PDF 高亮块 hover/focus -> 角标浮现 accent 环。
export function CitationChip({ citation }: { citation: Citation }) {
  const goTo = usePdfNav((s) => s.goTo);
  const active = usePdfNav((s) => s.activeCitation);
  const isActive = active === citation.index;
  const label = citationLabel(citation);
  const tooltip = citation.snippet ? `${label} — ${citation.snippet}` : label;

  return (
    <Tooltip content={tooltip}>
      <button
        type="button"
        onClick={() =>
          goTo({
            page: citation.page,
            bbox: citation.bbox,
            index: citation.index,
            docId: citation.docId,
          })
        }
        onMouseEnter={() => usePdfNav.getState().setActiveCitation(citation.index)}
        onMouseLeave={() => usePdfNav.getState().setActiveCitation(null)}
        onFocus={() => usePdfNav.getState().setActiveCitation(citation.index)}
        onBlur={() => usePdfNav.getState().setActiveCitation(null)}
        aria-label={`引用 ${citation.index}：${label}`}
        className={cn(
          'mx-0.5 inline-flex translate-y-[1px] items-center rounded-sm border border-citation bg-citation-bg px-1 align-baseline font-mono text-[11px] leading-none text-citation',
          'transition-[box-shadow,background-color] duration-150 ease-standard',
          'hover:bg-citation/20 focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]',
          isActive && 'shadow-[0_0_0_2px_var(--citation-ring)]',
        )}
      >
        {citation.index}
      </button>
    </Tooltip>
  );
}
