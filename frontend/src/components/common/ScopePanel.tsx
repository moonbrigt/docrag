import { FileText, X } from 'lucide-react';
import type { DocumentItem } from '@/types/api';
import { cn } from '@/lib/cn';
import { Spinner } from '@/components/ui/Spinner';
import { EmptyState } from '@/components/ui/EmptyState';

// 问答范围面板：仅展示 indexed + active 文档，多选限定检索范围；
// 点击文档名切换 PDF 预览；空知识库时给出引导。
export function ScopePanel({
  docsLoading,
  selectable,
  selectedIds,
  previewDocId,
  pendingDocs,
  onToggle,
  onPreview,
  onClear,
}: {
  docsLoading: boolean;
  selectable: DocumentItem[];
  selectedIds: string[];
  previewDocId: string | null;
  pendingDocs: number;
  onToggle: (id: string, checked: boolean) => void;
  onPreview: (id: string) => void;
  onClear: () => void;
}) {
  return (
    <aside className="hidden w-64 shrink-0 flex-col border-r border-line md:flex">
      <div className="flex items-center justify-between border-b border-line px-3 py-2">
        <span className="text-xs text-meta caps-label">问答范围</span>
        {selectedIds.length > 0 && (
          <button
            type="button"
            onClick={onClear}
            className="inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-xs text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none"
          >
            <X size={12} aria-hidden />
            清除
          </button>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2">
        {docsLoading ? (
          <div className="flex h-full items-center justify-center">
            <Spinner size={24} />
          </div>
        ) : selectable.length === 0 ? (
          <EmptyState
            icon={FileText}
            title="没有可检索的文档"
            description="文档完成索引后才会出现在这里。未选择范围时，提问将检索全部已索引文档。"
            className="py-10"
          />
        ) : (
          <>
            <ul className="space-y-1">
              {selectable.map((d) => (
                <li key={d.id}>
                  <label
                    className={cn(
                      'flex cursor-pointer items-start gap-2 rounded-sm border px-2 py-2 transition-colors',
                      previewDocId === d.id
                        ? 'border-accent bg-surface-2'
                        : 'border-transparent hover:bg-surface-2',
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={selectedIds.includes(d.id)}
                      onChange={(e) => onToggle(d.id, e.target.checked)}
                      className="mt-0.5 shrink-0 [accent-color:var(--accent)]"
                    />
                    <button
                      type="button"
                      onClick={() => onPreview(d.id)}
                      className="min-w-0 flex-1 text-left focus-visible:outline-none"
                    >
                      <span className="block truncate text-sm text-fg">{d.filename}</span>
                      <span className="mt-0.5 block text-xs text-meta">
                        {d.page_count ? `${d.page_count} 页` : '—'}
                        {d.version != null ? ` · v${d.version}` : ''}
                      </span>
                    </button>
                  </label>
                </li>
              ))}
            </ul>
            {pendingDocs > 0 && (
              <p className="mt-3 px-1 text-xs text-meta">
                {pendingDocs} 个文档仍在处理，完成索引后可加入范围。
              </p>
            )}
          </>
        )}
      </div>
    </aside>
  );
}
