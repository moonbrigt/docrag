import { NavLink } from 'react-router-dom';
import { cn } from '@/lib/cn';
import { NAV } from './nav';

export function Sidebar() {
  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-line bg-surface md:flex">
      <div className="flex h-16 items-center gap-2 px-5">
        <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-accent text-accent-on font-announce text-sm">
          D
        </span>
        <span className="text-md font-announce text-fg">DocRAG</span>
      </div>

      <nav className="flex flex-1 flex-col gap-1 px-3 py-2">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              cn(
                'relative flex items-center gap-3 rounded-sm px-3 py-2 text-sm transition-colors duration-150 ease-standard focus-visible:outline-none',
                isActive ? 'bg-surface-2 text-fg' : 'text-muted hover:bg-surface-2 hover:text-fg',
              )
            }
          >
            {({ isActive }) => (
              <>
                {isActive && (
                  <span className="absolute left-0 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-pill bg-accent" />
                )}
                <Icon size={20} strokeWidth={2} className={isActive ? 'text-accent' : ''} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="px-5 py-4 text-xs text-meta">可溯源文档问答 · v0.1</div>
    </aside>
  );
}
