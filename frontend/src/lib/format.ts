// 轻量格式化工具（中文语境）。

/** 相对时间（"2 小时前" / "3 天前"），用于最近问答、文档时间。 */
export function timeAgo(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return '';
  const diff = Date.now() - then;
  const sec = Math.floor(diff / 1000);
  if (sec < 60) return '刚刚';
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 30) return `${day} 天前`;
  const mon = Math.floor(day / 30);
  if (mon < 12) return `${mon} 个月前`;
  return `${Math.floor(mon / 12)} 年前`;
}

/** 千分位整数 */
export function formatCount(n: number): string {
  return n.toLocaleString('zh-CN');
}

/** 百分比（输入 0–1，输出带 % 字符串） */
export function formatPercent(ratio: number, digits = 1): string {
  return `${(ratio * 100).toFixed(digits)}%`;
}

/** 文件名去扩展名 */
export function stripExt(name: string): string {
  return name.replace(/\.[^./\\]+$/, '');
}

/** 截断中部文本（用于长文件名 / 文档名） */
export function truncateMiddle(text: string, max = 28): string {
  if (text.length <= max) return text;
  const keep = max - 1;
  const head = Math.ceil(keep / 2);
  const tail = Math.floor(keep / 2);
  return `${text.slice(0, head)}…${text.slice(text.length - tail)}`;
}
