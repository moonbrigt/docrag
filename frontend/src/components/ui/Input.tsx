import { forwardRef } from 'react';
import type { InputHTMLAttributes, TextareaHTMLAttributes } from 'react';
import { cn } from '@/lib/cn';

const fieldBase =
  'w-full bg-surface border border-line rounded-sm px-3 py-2.5 text-sm text-fg ' +
  'placeholder:text-meta transition-colors duration-150 ease-standard ' +
  'focus-visible:outline-none focus-visible:border-accent focus-visible:shadow-[var(--focus-ring)] ' +
  'disabled:opacity-45 disabled:pointer-events-none';

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return <input ref={ref} className={cn(fieldBase, className)} {...props} />;
  },
);

export const Textarea = forwardRef<
  HTMLTextAreaElement,
  TextareaHTMLAttributes<HTMLTextAreaElement>
>(function Textarea({ className, ...props }, ref) {
  return (
    <textarea ref={ref} className={cn(fieldBase, 'resize-none', className)} {...props} />
  );
});
