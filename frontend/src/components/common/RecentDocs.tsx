import { Link } from 'react-router-dom';
import { FileText } from 'lucide-react';
import type { DocumentItem } from '@/types/api';
import { formatCount } from '@/lib/format';

export function RecentDocs({ documents }: { documents: DocumentItem[] }) {
  const top = documents.slice(0, 4);
  if (top.length === 0) return null;

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {top.map((d) => (
        <Link
          key={d.id}
          to="/documents"
          className="group rounded-md border border-line bg-surface p-4 transition-colors hover:border-accent focus-visible:outline-none"
        >
          <div className="flex items-center gap-2">
            <FileText size={20} className="shrink-0 text-meta transition-colors group-hover:text-accent" />
            <span className="truncate text-sm font-emphasize text-fg">{d.filename}</span>
          </div>
          <p className="mt-2 font-mono text-xs text-meta">
            {d.page_count ? `${d.page_count} 页` : '—'} · {formatCount(d.chunk_count ?? 0)} 分块
          </p>
        </Link>
      ))}
    </div>
  );
}
