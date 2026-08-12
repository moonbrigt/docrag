import { useEffect, useRef, useState } from 'react';
import { AlertTriangle, ChevronLeft, ChevronRight, FileText, ZoomIn, ZoomOut } from 'lucide-react';
import type { PDFDocumentProxy } from 'pdfjs-dist';
import { pdfjsLib } from '@/lib/pdf';
import { getDocumentFileUrl } from '@/api/documents';
import { usePdfNav, type HighlightTarget } from '@/lib/stores';
import type { Bbox } from '@/types/api';
import { EmptyState } from '@/components/ui/EmptyState';
import { Spinner } from '@/components/ui/Spinner';

type Status = 'idle' | 'loading' | 'ready' | 'error';

interface Highlight {
  page: number;
  bbox?: Bbox;
  index?: number;
}

export function PDFPreview({
  docId,
  onNavigateDoc,
}: {
  docId: string | null;
  onNavigateDoc?: (docId: string) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const onNavigateDocRef = useRef(onNavigateDoc);
  onNavigateDocRef.current = onNavigateDoc;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const currentDocRef = useRef<string | null>(null);
  const navTargetRef = useRef<Highlight | null>(null);
  const loadTaskRef = useRef<{ destroy: () => void } | null>(null);
  const renderTaskRef = useRef<{ cancel: () => void } | null>(null);

  const [pdfDoc, setPdfDoc] = useState<PDFDocumentProxy | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [pageNumber, setPageNumber] = useState(1);
  const [zoom, setZoom] = useState(1);
  const [status, setStatus] = useState<Status>('idle');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [canvasSize, setCanvasSize] = useState({ w: 0, h: 0 });
  const [highlight, setHighlight] = useState<Highlight | null>(null);

  // 注册 PDF 导航（由 CitationChip 调用）
  useEffect(() => {
    const handler = (target: HighlightTarget) => {
      navTargetRef.current = { page: target.page, bbox: target.bbox, index: target.index };
      if (target.docId && target.docId !== currentDocRef.current) {
        onNavigateDocRef.current?.(target.docId); // 切文档：由父级更新 docId，load effect 随后应用页码/高亮
      } else {
        setPageNumber(target.page);
        setHighlight({ page: target.page, bbox: target.bbox, index: target.index });
      }
    };
    usePdfNav.getState().registerNavigate(handler);
    return () => usePdfNav.getState().registerNavigate(null);
  }, []);

  // docId 变化 -> 加载 PDF 文档
  useEffect(() => {
    if (!docId) {
      currentDocRef.current = null;
      setPdfDoc(null);
      setNumPages(0);
      setStatus('idle');
      return;
    }
    currentDocRef.current = docId;
    let cancelled = false;
    setStatus('loading');
    setErrorMsg(null);
    setPdfDoc(null);
    setNumPages(0);
    setPageNumber(1);
    setHighlight(null);

    const task = pdfjsLib.getDocument({ url: getDocumentFileUrl(docId), withCredentials: false });
    loadTaskRef.current = task;
    task.promise
      .then((pdf) => {
        if (cancelled) return;
        setPdfDoc(pdf);
        setNumPages(pdf.numPages);
        const tgt = navTargetRef.current;
        if (tgt) {
          setPageNumber(tgt.page);
          setHighlight({ page: tgt.page, bbox: tgt.bbox, index: tgt.index });
        }
        setStatus('ready');
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setErrorMsg(e instanceof Error ? e.message : 'PDF 加载失败');
        setStatus('error');
      });

    return () => {
      cancelled = true;
      try {
        task.destroy();
      } catch {
        /* ignore */
      }
    };
  }, [docId]);

  // 渲染当前页到 canvas（缩放适配容器宽度）
  useEffect(() => {
    if (status !== 'ready' || !pdfDoc) return;
    let cancelled = false;
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext('2d');
    if (!canvas || !ctx) return;

    pdfDoc
      .getPage(pageNumber)
      .then((page) => {
        if (cancelled) return;
        const containerWidth = containerRef.current?.clientWidth ?? 800;
        const available = Math.max(280, containerWidth - 32);
        const base = page.getViewport({ scale: 1 });
        const scale = (available / base.width) * zoom;
        const viewport = page.getViewport({ scale });
        canvas.width = Math.floor(viewport.width);
        canvas.height = Math.floor(viewport.height);
        canvas.style.width = `${Math.floor(viewport.width)}px`;
        canvas.style.height = `${Math.floor(viewport.height)}px`;
        setCanvasSize({ w: viewport.width, h: viewport.height });
        renderTaskRef.current?.cancel();
        const rt = page.render({ canvas, viewport });
        renderTaskRef.current = rt;
        rt.promise.catch(() => {
          /* 渲染被取消属正常 */
        });
      })
      .catch(() => {
        /* 页面获取失败（页码越界等） */
      });

    return () => {
      cancelled = true;
    };
  }, [pdfDoc, pageNumber, status, zoom]);

  if (status === 'idle') {
    return (
      <EmptyState
        icon={FileText}
        title="暂无文档可预览"
        description="在左侧文档面板上传或选择文档后，此处显示 PDF 原文与引用高亮。"
      />
    );
  }

  if (status === 'loading') {
    return (
      <div className="flex h-full items-center justify-center">
        <Spinner size={28} />
      </div>
    );
  }

  if (status === 'error') {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 px-6 text-center">
        <AlertTriangle size={24} className="text-danger" />
        <p className="text-sm text-danger">PDF 渲染失败</p>
        <p className="max-w-xs text-xs text-meta">{errorMsg ?? '无法加载文档原文。'}</p>
      </div>
    );
  }

  const goPrev = () => {
    setHighlight(null);
    setPageNumber((p) => Math.max(1, p - 1));
  };
  const goNext = () => {
    setHighlight(null);
    setPageNumber((p) => Math.min(numPages, p + 1));
  };

  const showHighlight = highlight && highlight.page === pageNumber;

  return (
    <div className="flex h-full flex-col">
      {/* 顶部页码导航 */}
      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-line bg-surface px-3 py-2">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={goPrev}
            disabled={pageNumber <= 1}
            aria-label="上一页"
            className="rounded-sm p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none disabled:opacity-40"
          >
            <ChevronLeft size={18} />
          </button>
          <span className="font-mono text-sm text-fg">
            p.{pageNumber} / {numPages}
          </span>
          <button
            type="button"
            onClick={goNext}
            disabled={pageNumber >= numPages}
            aria-label="下一页"
            className="rounded-sm p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none disabled:opacity-40"
          >
            <ChevronRight size={18} />
          </button>
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setZoom((z) => Math.max(0.6, +(z - 0.15).toFixed(2)))}
            aria-label="缩小"
            className="rounded-sm p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none"
          >
            <ZoomOut size={16} />
          </button>
          <span className="w-10 text-center font-mono text-xs text-meta">{Math.round(zoom * 100)}%</span>
          <button
            type="button"
            onClick={() => setZoom((z) => Math.min(2.5, +(z + 0.15).toFixed(2)))}
            aria-label="放大"
            className="rounded-sm p-1.5 text-muted transition-colors hover:bg-surface-2 hover:text-fg focus-visible:outline-none"
          >
            <ZoomIn size={16} />
          </button>
        </div>
      </div>

      {/* PDF 画布 */}
      <div ref={containerRef} className="flex-1 overflow-auto bg-surface-2 p-4">
        <div className="relative mx-auto w-fit shadow-elev-raised">
          <canvas ref={canvasRef} className="block" />
          {showHighlight &&
            (highlight!.bbox ? (
              <button
                type="button"
                onMouseEnter={() => highlight!.index != null && usePdfNav.getState().setActiveCitation(highlight!.index)}
                onMouseLeave={() => usePdfNav.getState().setActiveCitation(null)}
                onFocus={() => highlight!.index != null && usePdfNav.getState().setActiveCitation(highlight!.index)}
                onBlur={() => usePdfNav.getState().setActiveCitation(null)}
                aria-label={`引用 ${highlight!.index} 高亮区域`}
                className="absolute border border-citation bg-citation-fill animate-pulse-cite focus-visible:outline-none"
                style={{
                  left: `${highlight!.bbox.left * canvasSize.w}px`,
                  top: `${highlight!.bbox.top * canvasSize.h}px`,
                  width: `${(highlight!.bbox.right - highlight!.bbox.left) * canvasSize.w}px`,
                  height: `${(highlight!.bbox.bottom - highlight!.bbox.top) * canvasSize.h}px`,
                }}
              />
            ) : (
              <div
                aria-hidden
                className="pointer-events-none absolute inset-0 border-t-2 border-accent bg-citation-fill animate-pulse-cite"
              />
            ))}
        </div>
      </div>

      {/* 跳转播报（反向联动 / 可访问性） */}
      <div aria-live="polite" className="sr-only">
        {showHighlight
          ? `已跳转至第 ${pageNumber} 页${highlight!.bbox ? '，已高亮段落' : ''}`
          : ''}
      </div>
    </div>
  );
}
