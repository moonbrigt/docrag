// 本地最近提问（localStorage）。无后端历史接口时，用于首页"最近问答"真实展示。

export interface RecentQuery {
  id: string;
  query: string;
  at: number;
}

const KEY = 'docrag-recent-queries';
const MAX = 6;

export function getRecentQueries(): RecentQuery[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const list = JSON.parse(raw) as RecentQuery[];
    return Array.isArray(list) ? list : [];
  } catch {
    return [];
  }
}

export function addRecentQuery(query: string): void {
  const q = query.trim();
  if (!q) return;
  const list = getRecentQueries().filter((item) => item.query !== q);
  list.unshift({ id: crypto.randomUUID(), query: q, at: Date.now() });
  try {
    localStorage.setItem(KEY, JSON.stringify(list.slice(0, MAX)));
  } catch {
    /* 忽略存储失败 */
  }
}
