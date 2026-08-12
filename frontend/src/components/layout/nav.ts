import type { LucideIcon } from 'lucide-react';
import { BarChart3, FileText, Home, MessageSquare, Settings } from 'lucide-react';

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  end?: boolean;
}

// 全局导航（暗色 chrome，图标 20px + 文字；移动端底部 TabBar 复用）
export const NAV: NavItem[] = [
  { to: '/', label: '概览', icon: Home, end: true },
  { to: '/documents', label: '文档库', icon: FileText },
  { to: '/chat', label: '问答', icon: MessageSquare },
  { to: '/evaluation', label: '评测看板', icon: BarChart3 },
  { to: '/settings', label: '设置', icon: Settings },
];
