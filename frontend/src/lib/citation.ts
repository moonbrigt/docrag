// 将回答文本中的内联 [n] 引用标记解析为可渲染片段。
// 片段分两类：text（普通文本）与 cite（引用角标，含 1-based 序号）。

import type { Citation } from '@/types/api';

export type Segment =
  | { kind: 'text'; text: string }
  | { kind: 'cite'; text: string; index: number };

const CITE_RE = /\[(\d+)\]/g;

export function parseCitations(content: string): Segment[] {
  const out: Segment[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  CITE_RE.lastIndex = 0;
  while ((match = CITE_RE.exec(content)) !== null) {
    if (match.index > last) {
      out.push({ kind: 'text', text: content.slice(last, match.index) });
    }
    out.push({ kind: 'cite', text: match[0], index: Number.parseInt(match[1], 10) });
    last = match.index + match[0].length;
  }
  if (last < content.length) {
    out.push({ kind: 'text', text: content.slice(last) });
  }
  return out;
}

/** 引用展示标签：来源标题 · v版本 · p.页码（新旧字段名均容错） */
export function citationLabel(c: Citation): string {
  const title = c.title || c.docName || '未知来源';
  const version = c.version != null && c.version !== '' ? ` · v${c.version}` : '';
  const page = c.page > 0 ? ` · p.${c.page}` : '';
  return `${title}${version}${page}`;
}
