import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';
import type { BadgeTone } from '@/lib/status';

const toneStyles: Record<BadgeTone, string> = {
  neutral: 'text-meta border-line',
  success: 'text-success border-success/40 bg-success/10',
  accent: 'text-accent border-accent/40 bg-accent/10',
  warn: 'text-warn border-warn/40 bg-warn/10',
  danger: 'text-danger border-danger/40 bg-danger/10',
};

const dotColor: Record<BadgeTone, string> = {
  neutral: 'bg-meta',
  success: 'bg-success',
  accent: 'bg-accent',
  warn: 'bg-warn',
  danger: 'bg-danger',
};

export interface BadgeProps {
  tone?: BadgeTone;
  dot?: boolean;
  children: ReactNode;
  className?: string;
}

export function Badge({ tone = 'neutral', dot = false, children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-pill border px-2 py-0.5 text-xs caps-label',
        toneStyles[tone],
        className,
      )}
    >
      {dot && <span className={cn('h-1.5 w-1.5 rounded-pill', dotColor[tone])} aria-hidden />}
      {children}
    </span>
  );
}
