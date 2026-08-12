import { useRef, useState } from 'react';
import { FileWarning, Upload } from 'lucide-react';
import { useUploadDocument } from '@/hooks/useDocuments';
import { extractErrorMessage } from '@/api/client';
import { Spinner } from '@/components/ui/Spinner';
import { cn } from '@/lib/cn';

const MAX_SIZE = 200 * 1024 * 1024; // 200MB

export function UploadDropzone({
  compact = false,
  onUploaded,
}: {
  compact?: boolean;
  onUploaded?: () => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const upload = useUploadDocument();
  const [localBusy, setLocalBusy] = useState(false);
  const busy = localBusy || upload.isPending;

  const handleFiles = async (files: FileList | null) => {
    setError(null);
    const file = files?.[0];
    if (!file) return;
    const isPdf = file.type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      setError('仅支持 PDF 格式');
      return;
    }
    if (file.size > MAX_SIZE) {
      setError('文件超过 200MB 上限');
      return;
    }
    try {
      setLocalBusy(true);
      await upload.mutateAsync(file);
      onUploaded?.();
    } catch (e) {
      setError(extractErrorMessage(e, '上传失败，请重试'));
    } finally {
      setLocalBusy(false);
    }
  };

  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => !busy && inputRef.current?.click()}
      onKeyDown={(e) => {
        if ((e.key === 'Enter' || e.key === ' ') && !busy) {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!busy) setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        if (!busy) handleFiles(e.dataTransfer.files);
      }}
      className={cn(
        'group flex cursor-pointer flex-col items-center justify-center gap-2 rounded-md border border-dashed border-line text-center',
        'px-4 transition-colors duration-150 ease-standard focus-visible:outline-none',
        compact ? 'py-5' : 'py-10',
        dragging ? 'border-accent bg-accent/10' : 'hover:border-accent',
        busy && 'pointer-events-none opacity-60',
      )}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf"
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      {busy ? (
        <Spinner size={24} />
      ) : (
        <Upload size={compact ? 20 : 24} className="text-meta transition-colors group-hover:text-accent" />
      )}
      <p className={cn('font-emphasize text-fg', compact ? 'text-sm' : 'text-md')}>
        {busy ? '正在加入解析队列…' : '拖入 PDF 开始构建知识库'}
      </p>
      {!busy && <p className="text-xs text-meta">或点击选择文件 · 单文件 ≤ 200MB</p>}
      {error && (
        <p className="mt-1 flex items-center gap-1 text-xs text-danger">
          <FileWarning size={14} />
          {error}
        </p>
      )}
    </div>
  );
}
