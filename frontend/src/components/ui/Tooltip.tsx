import * as RT from '@radix-ui/react-tooltip';
import type { ReactNode } from 'react';

export interface TooltipProps {
  content: ReactNode;
  children: ReactNode;
  side?: 'top' | 'right' | 'bottom' | 'left';
}

// 轻量 Tooltip 封装（引用角标、状态点等使用）。
export function Tooltip({ content, children, side = 'top' }: TooltipProps) {
  return (
    <RT.Provider delayDuration={150}>
      <RT.Root>
        <RT.Trigger asChild>{children}</RT.Trigger>
        <RT.Portal>
          <RT.Content
            side={side}
            sideOffset={6}
            className="z-50 max-w-xs rounded-sm border border-line bg-surface-3 px-2.5 py-1.5 text-xs text-fg shadow-elev-raised animate-fade-in"
          >
            {content}
            <RT.Arrow className="fill-[var(--surface-3)]" />
          </RT.Content>
        </RT.Portal>
      </RT.Root>
    </RT.Provider>
  );
}
