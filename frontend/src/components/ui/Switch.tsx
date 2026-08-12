import * as Switch from '@radix-ui/react-switch';
import { cn } from '@/lib/cn';

export interface ToggleProps {
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
  id?: string;
  disabled?: boolean;
  'aria-label'?: string;
}

export function Toggle({ checked, onCheckedChange, id, disabled, ...rest }: ToggleProps) {
  return (
    <Switch.Root
      id={id}
      checked={checked}
      onCheckedChange={onCheckedChange}
      disabled={disabled}
      className={cn(
        'relative h-5 w-9 shrink-0 rounded-pill border border-line bg-surface-2',
        'transition-colors duration-150 ease-standard focus-visible:outline-none',
        'disabled:opacity-45 disabled:pointer-events-none',
        'data-[state=checked]:border-accent data-[state=checked]:bg-accent',
      )}
      {...rest}
    >
      <Switch.Thumb
        className={cn(
          'block h-4 w-4 translate-x-0.5 rounded-pill bg-fg transition-transform duration-150 ease-standard',
          'data-[state=checked]:translate-x-[18px] data-[state=checked]:bg-accent-on',
        )}
      />
    </Switch.Root>
  );
}
