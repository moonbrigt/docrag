import * as Dialog from '@radix-ui/react-dialog';
import { X } from 'lucide-react';
import type { ReactNode } from 'react';
import { cn } from '@/lib/cn';

export interface DialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title?: ReactNode;
  description?: ReactNode;
  children?: ReactNode;
  footer?: ReactNode;
  side?: 'center' | 'right';
}

// Radix Dialog：center = 居中对话框（删除确认等）；right = 右侧抽屉（文档详情）。
export function AppDialog({
  open,
  onOpenChange,
  title,
  description,
  children,
  footer,
  side = 'center',
}: DialogProps) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-sm animate-fade-in" />
        <Dialog.Content
          className={cn(
            'fixed z-50 bg-surface border border-line shadow-elev-raised focus-visible:outline-none',
            side === 'right'
              ? 'right-0 top-0 h-full w-full max-w-md flex flex-col animate-slide-in-right'
              : 'left-1/2 top-1/2 max-h-[85vh] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-md p-6 animate-fade-in',
          )}
        >
          {(title || description) && (
            <div className="mb-4 flex items-start justify-between gap-4">
              <div className="space-y-1">
                {title && (
                  <Dialog.Title className="text-md font-emphasize text-fg">{title}</Dialog.Title>
                )}
                {description && (
                  <Dialog.Description className="text-sm text-muted">{description}</Dialog.Description>
                )}
              </div>
              <Dialog.Close
                className="rounded-sm p-1 text-meta transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none"
                aria-label="关闭"
              >
                <X size={20} />
              </Dialog.Close>
            </div>
          )}
          <div className={cn(side === 'center' && 'space-y-4')}>{children}</div>
          {footer && <div className="mt-6 flex justify-end gap-2">{footer}</div>}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
