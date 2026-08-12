import { create } from 'zustand';
import type { Bbox } from '@/types/api';

// =============================================================================
// 跨组件联动状态：
// 1) PDF 导航：CitationChip 点击 -> 调用 PDFPreview 注册的 navigate(target)
// 2) 引用反向联动：PDF 内高亮块 hover/focus -> 对话中对应角标浮现 accent 环
// =============================================================================

export interface HighlightTarget {
  page: number;
  bbox?: Bbox;
  index?: number;
  docId?: string;
}

type NavigateFn = (target: HighlightTarget) => void;

interface PdfNavState {
  navigate: NavigateFn | null;
  registerNavigate: (fn: NavigateFn | null) => void;
  goTo: (target: HighlightTarget) => void;

  activeCitation: number | null;
  setActiveCitation: (index: number | null) => void;
}

export const usePdfNav = create<PdfNavState>((set, get) => ({
  navigate: null,
  registerNavigate: (fn) => set({ navigate: fn }),
  goTo: (target) => {
    const fn = get().navigate;
    if (fn) fn(target);
  },
  activeCitation: null,
  setActiveCitation: (index) => set({ activeCitation: index }),
}));
