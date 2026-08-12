import { useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  AlertCircle,
  FileText,
  FileUp,
  LoaderCircle,
  Lock,
  RotateCcw,
  Search,
  Square,
  Trash2,
} from 'lucide-react';
import type { DocumentItem, DocStatus } from '@/types/api';
import { docStatusMeta } from '@/lib/status';
import { cn } from '@/lib/cn';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { EmptyState } from '@/components/ui/EmptyState';
import { AppDialog } from '@/components/ui/Dialog';
import { Input } from '@/components/ui/Input';
import { Stepper } from './Stepper';
import { AclDialog } from './AclDialog';
import { VersionUploadDialog } from './VersionUploadDialog';
import { formatCount, timeAgo } from '@/lib/format';

const PROCESSING: DocStatus[] = ['queued', 'parsing', 'chunking', 'embedding'];
const RETRYABLE: DocStatus[] = ['warning', 'failed', 'cancelled'];
const COLUMNS = 'grid-cols-[1fr_52px_52px_56px_150px_148px]';

interface DocTableProps {
  documents: DocumentItem[];
  isLoading: boolean;
  isError: boolean;
  onRetry: () => void;
  onSelect: (doc: DocumentItem) => void;
  onDelete: (id: string) => void;
  deletePending?: boolean;
  cancelPending?: boolean;
  retryPending?: boolean;
  onCancel: (id: string) => void;
  onRetryDoc: (id: string) => void;
  onUploadVersion: (id: string, file: File) => Promise<unknown>;
}

export function DocTable({
  documents,
  isLoading,
  isError,
  onRetry,
  onSelect,
  onDelete,
  deletePending,
  cancelPending,
  retryPending,
  onCancel,
  onRetryDoc,
  onUploadVersion,
}: DocTableProps) {
  const [query, setQuery] = useState('');
  const [pendingDelete, setPendingDelete] = useState<DocumentItem | null>(null);
  const [versionDoc, setVersionDoc] = useState<DocumentItem | null>(null);
  const [aclDoc, setAclDoc] = useState<DocumentItem | null>(null);

  const filtered = useMemo(
    () => documents.filter((d) => d.filename.toLowerCase().includes(query.toLowerCase())),
    [documents, query],
  );

  // live region：状态变化播报（role=status；失败/警告走 role=alert）
  const prevStatusRef = useRef<Record<string, DocStatus>>({});
  const [announce, setAnnounce] = useState<{ text: string; alert: boolean } | null>(null);
  useEffect(() => {
    const parts: string[] = [];
    let alert = false;
    for (const d of documents) {
      const prev = prevStatusRef.current[d.id];
      if (prev && prev !== d.status) {
        const meta = docStatusMeta(d.status, d.error);
        parts.push(`文档「${d.filename}」${meta.label}${d.error ? `：${d.error}` : ''}`);
        if (d.status === 'failed' || d.status === 'warning') alert = true;
      }
      prevStatusRef.current[d.id] = d.status;
    }
    if (parts.length > 0) setAnnounce({ text: parts.join('；'), alert });
  }, [documents]);

  if (isError) {
    return (
      <div className="rounded-md border border-danger/40 bg-danger/5 p-6">
        <div className="flex items-center gap-2 text-danger">
          <AlertCircle size={18} />
          <span>加载文档失败</span>
        </div>
        <Button variant="secondary" size="sm" className="mt-3" onClick={onRetry} leadingIcon={<LoaderCircle size={16} className="animate-spin" />}>重试</Button>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-16 animate-pulse rounded-md border border-line bg-surface" />
        ))}
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <EmptyState
        icon={FileText}
        title="拖入 PDF，开始构建你的可溯源知识库"
        description="支持可提取文本的 PDF，解析后每段都带页码与溯源元数据。"
        action={<p className="text-xs text-meta">单文件 ≤ 200MB</p>}
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="relative max-w-sm">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-meta" />
        <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="搜索文档名…" className="pl-9" />
      </div>

      <div className="overflow-x-auto rounded-md border border-line">
        <div className="min-w-[760px]">
          <div className={cn('grid gap-3 border-b border-line bg-surface-2 px-4 py-2 text-xs text-meta caps-label', COLUMNS)}>
            <span>名称 / 版本</span>
            <span>页数</span>
            <span>分块</span>
            <span>版本</span>
            <span>状态</span>
            <span className="text-right">操作</span>
          </div>
          <ul className="divide-y divide-line-soft">
            {filtered.map((doc) => {
              const meta = docStatusMeta(doc.status, doc.error);
              const processing = PROCESSING.includes(doc.status);
              const retryable = RETRYABLE.includes(doc.status);
              return (
                <li key={doc.id}>
                  <div className={cn('grid items-center gap-3 px-4 py-3', COLUMNS)}>
                    <div className="flex min-w-0 items-center gap-3">
                      <FileText size={20} className="shrink-0 text-meta" aria-hidden />
                      <div className="min-w-0">
                        <button
                          type="button"
                          onClick={() => onSelect(doc)}
                          className="block w-full truncate text-left text-sm text-fg transition-colors hover:text-accent focus-visible:outline-none"
                        >
                          {doc.filename}
                        </button>
                        <p className="mt-0.5 text-xs text-meta">
                          {doc.created_at ? timeAgo(doc.created_at) : '—'}
                          {doc.is_active === false && <span className="ml-1 text-meta">（非当前版本）</span>}
                        </p>
                      </div>
                    </div>
                    <span className="font-mono text-sm text-muted">{doc.page_count ?? '—'}</span>
                    <span className="font-mono text-sm text-muted">{formatCount(doc.chunk_count ?? 0)}</span>
                    <span className="flex items-center gap-1 font-mono text-sm text-muted">
                      {doc.version ?? '—'}
                      {doc.is_active && <Badge tone="success" className="!px-1 !py-0 !text-[10px]">当前</Badge>}
                    </span>
                    <span>
                      {processing ? (
                        <Stepper status={doc.status} error={doc.error} />
                      ) : (
                        <Badge tone={meta.tone}>{meta.label}</Badge>
                      )}
                    </span>
                    <span className="flex items-center justify-end gap-1">
                      {processing && (
                        <RowAction
                          title="取消处理"
                          busy={cancelPending}
                          onClick={() => onCancel(doc.id)}
                        >
                          <Square size={14} />
                        </RowAction>
                      )}
                      {retryable && (
                        <RowAction
                          title="重新处理"
                          busy={retryPending}
                          onClick={() => onRetryDoc(doc.id)}
                        >
                          <RotateCcw size={14} />
                        </RowAction>
                      )}
                      <RowAction title="上传替换版本" onClick={() => setVersionDoc(doc)}>
                        <FileUp size={14} />
                      </RowAction>
                      <RowAction title="管理访问权限" onClick={() => setAclDoc(doc)}>
                        <Lock size={14} />
                      </RowAction>
                      <RowAction title="删除文档" danger onClick={() => setPendingDelete(doc)}>
                        <Trash2 size={14} />
                      </RowAction>
                    </span>
                  </div>
                  {(doc.status === 'failed' || doc.status === 'warning') && doc.error && (
                    <div className="flex items-center gap-2 bg-danger/5 px-4 py-2 text-xs text-danger">
                      <AlertCircle size={14} className="shrink-0" aria-hidden />
                      <span className="min-w-0 flex-1 truncate">{doc.error}</span>
                      <button
                        type="button"
                        onClick={() => setPendingDelete(doc)}
                        className="shrink-0 underline focus-visible:outline-none"
                      >
                        移除
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      </div>

      {/* live region：状态变化播报（role=status 常规，失败/警告 role=alert） */}
      <div role="status" className="sr-only">{announce && !announce.alert ? announce.text : ''}</div>
      <div role="alert" className="sr-only">{announce?.alert ? announce.text : ''}</div>

      <AppDialog
        open={!!pendingDelete}
        onOpenChange={(o) => !o && setPendingDelete(null)}
        title="删除文档"
        description={`确定删除「${pendingDelete?.filename}」？对应的向量与全文索引将一并清理。`}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)}>
              取消
            </Button>
            <Button
              variant="danger"
              loading={deletePending}
              onClick={() => pendingDelete && onDelete(pendingDelete.id)}
            >
              删除
            </Button>
          </>
        }
      >
        <p className="text-sm text-muted">此操作不可撤销。</p>
      </AppDialog>

      <VersionUploadDialog
        doc={versionDoc}
        open={!!versionDoc}
        onOpenChange={(o) => !o && setVersionDoc(null)}
        onUpload={onUploadVersion}
      />

      <AclDialog
        doc={aclDoc}
        open={!!aclDoc}
        onOpenChange={(o) => !o && setAclDoc(null)}
      />
    </div>
  );
}

function RowAction({
  title,
  onClick,
  busy,
  danger,
  children,
}: {
  title: string;
  onClick: () => void;
  busy?: boolean;
  danger?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      disabled={busy}
      className={cn(
        'rounded-sm p-1.5 text-meta transition-colors hover:bg-surface-3 focus-visible:outline-none',
        danger ? 'hover:text-danger' : 'hover:text-fg',
        busy && 'opacity-40',
      )}
    >
      {busy ? <LoaderCircle size={14} className="animate-spin" aria-hidden /> : children}
    </button>
  );
}
