import type { DocStatus } from '@/types/api';

export type BadgeTone = 'neutral' | 'success' | 'accent' | 'warn' | 'danger';

// 文档状态 -> 徽章语义色 + 中文标签（具体文案，禁模板味）
export function docStatusMeta(
  status: DocStatus,
  error?: string | null,
): { label: string; tone: BadgeTone } {
  switch (status) {
    case 'indexed':
      return { label: '已索引', tone: 'success' };
    case 'queued':
      return { label: '排队中', tone: 'neutral' };
    case 'parsing':
      return { label: '解析中', tone: 'accent' };
    case 'chunking':
      return { label: '分块中', tone: 'accent' };
    case 'embedding':
      return { label: '嵌入中', tone: 'accent' };
    case 'warning':
      return { label: '有警告', tone: 'warn' };
    case 'failed':
      return { label: error ? '失败' : '失败', tone: 'danger' };
    case 'cancelled':
      return { label: '已取消', tone: 'neutral' };
    default:
      return { label: status, tone: 'neutral' };
  }
}
