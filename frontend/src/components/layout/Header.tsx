import { ThemeToggle } from './ThemeToggle';

export function Header() {
  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-line bg-canvas/80 px-4 backdrop-blur md:px-6">
      <div className="flex items-center gap-2 md:hidden">
        <span className="flex h-7 w-7 items-center justify-center rounded-sm bg-accent text-accent-on font-announce text-sm">
          D
        </span>
        <span className="text-md font-announce text-fg">DocRAG</span>
      </div>
      <div className="hidden text-sm text-meta md:block">
        私有部署 · 带精准页码溯源的文档问答
      </div>
      <div className="flex items-center gap-2">
        <ThemeToggle />
      </div>
    </header>
  );
}
