import { LoaderCircle } from 'lucide-react';
import { cn } from '@/lib/cn';

export function Spinner({ size = 20, className }: { size?: number; className?: string }) {
  return (
    <LoaderCircle size={size} className={cn('animate-spin text-muted', className)} aria-hidden />
  );
}
