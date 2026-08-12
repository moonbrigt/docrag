import { Link } from 'react-router-dom';
import { ArrowRight, MessageSquare } from 'lucide-react';
import { getRecentQueries } from '@/lib/recentQueries';
import { timeAgo } from '@/lib/format';

// 最近问答：读取本会话 localStorage 中真实提交过的问题（无后端历史接口时的真实展示）。
export function RecentChats() {
  const items = getRecentQueries();

  if (items.length === 0) {
    return (
      <div className="rounded-md border border-line bg-surface p-4 text-sm text-muted">
        还没有问答记录。前往
        <Link to="/chat" className="text-accent">
          问答
        </Link>
        开始第一次提问。
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {items.map((q) => (
        <li key={q.id}>
          <Link
            to={`/chat?q=${encodeURIComponent(q.query)}`}
            className="group flex items-center gap-3 rounded-md border border-line bg-surface px-4 py-3 transition-colors hover:border-accent focus-visible:outline-none"
          >
            <MessageSquare size={16} className="shrink-0 text-meta transition-colors group-hover:text-accent" />
            <span className="min-w-0 flex-1 truncate text-sm text-fg">{q.query}</span>
            <span className="shrink-0 text-xs text-meta">{timeAgo(new Date(q.at).toISOString())}</span>
            <ArrowRight
              size={16}
              className="shrink-0 text-meta opacity-0 transition-opacity group-hover:opacity-100"
            />
          </Link>
        </li>
      ))}
    </ul>
  );
}
