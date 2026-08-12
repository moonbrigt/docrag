import { useRef, useState } from 'react';
import { FileUp } from 'lucide-react';
import type { DocumentItem } from '@/types/api';
import { extractErrorMessage } from '@/api/client';
import { AppDialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';

const MAX_SIZE = 200 * 1024 * 1024; // 200MB

// 上传替换版本：POST /documents/{id}/versions（multipart），
// 新版本解析完成后成为 active，来源记录与历史版本保留。
export function VersionUploadDialog({
  doc,
  open,
  onOpenChange,
  onUpload,
}: {
  doc: DocumentItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onUpload: (id: string, file: File) => Promise<unknown>;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const pick = (f: File | null) => {
    setError(null);
    if (!f) return;
    const isPdf = f.type === 'application/pdf' || f.name.toLowerCase().endsWith('.pdf');
    if (!isPdf) {
      setError('仅支持 PDF 格式');
      return;
    }
    if (f.size > MAX_SIZE) {
      setError('文件超过 200MB 上限');
      return;
    }
    setFile(f);
  };

  const submit = async () => {
    if (!doc || !file) return;
    setBusy(true);
    setError(null);
    try {
      await onUpload(doc.id, file);
      setFile(null);
      onOpenChange(false);
    } catch (e) {
      setError(extractErrorMessage(e, '上传新版本失败'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) {
          setFile(null);
          setError(null);
        }
        onOpenChange(o);
      }}
      title="上传替换版本"
      description={`为「${doc?.filename ?? ''}」上传新 PDF。当前版本 v${doc?.version ?? '?'} 将被替换，来源记录与引用历史保留。`}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button loading={busy} disabled={!file} onClick={submit} leadingIcon={<FileUp size={14} />}>
            上传新版本
          </Button>
        </>
      }
    >
      <div className="space-y-3">
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
          className="flex cursor-pointer flex-col items-center justify-center gap-1 rounded-md border border-dashed border-line px-4 py-6 text-center transition-colors hover:border-accent focus-visible:outline-none"
        >
          <input
            ref={inputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
          <FileUp size={20} className="text-meta" aria-hidden />
          <p className="text-sm text-fg">{file ? file.name : '点击选择新 PDF'}</p>
          {file && <p className="text-xs text-meta">{(file.size / 1024 / 1024).toFixed(1)} MB</p>}
        </div>
        <p className="text-xs text-meta">新版本将重新进入解析流水线（queued → … → indexed），完成后自动标记为当前版本。</p>
        {error && <p className="text-sm text-danger">{error}</p>}
      </div>
    </AppDialog>
  );
}
