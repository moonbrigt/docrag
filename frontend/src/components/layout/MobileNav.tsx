import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { NAV } from './nav';

// 移动端底部 TabBar（≤5 项，图标 24px + 文字 10px）
export function MobileNav() {
  return (
    <nav className="flex shrink-0 border-t border-line bg-surface md:hidden">
      {NAV.map(({ to, label, icon: Icon, end }) => (
        <NavLink
          key={to}
          to={to}
          end={end}
          className={({ isActive }) =>
            cn(
              'flex flex-1 flex-col items-center gap-0.5 py-2 text-[10px] transition-colors focus-visible:outline-none',
              isActive ? 'text-accent' : 'text-meta',
            )
          }
        >
          <Icon size={24} strokeWidth={2} />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}
