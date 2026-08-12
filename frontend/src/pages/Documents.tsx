import { useNavigate } from 'react-router-dom';
import { DocTable } from '@/components/common/DocTable';
import {
  useCancelDocument,
  useDeleteDocument,
  useDocuments,
  useRetryDocument,
  useUploadDocumentVersion,
} from '@/hooks/useDocuments';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card';

export function Documents() {
  const navigate = useNavigate();
  const { data: documents = [], isLoading, isError, refetch } = useDocuments();
  const del = useDeleteDocument();
  const cancel = useCancelDocument();
  const retryDoc = useRetryDocument();
  const uploadVersion = useUploadDocumentVersion();

  return (
    <div className="mx-auto w-full max-w-[var(--container-max)] space-y-6 px-4 py-6 md:px-6">
      <div>
        <h1 className="text-2xl font-announce text-fg">文档库</h1>
        <p className="mt-1 text-sm text-muted">
          管理已上传的 PDF、解析流水线状态与来源版本；失败/已取消的文档可重新处理。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>全部文档</CardTitle>
        </CardHeader>
        <CardBody>
          <DocTable
            documents={documents}
            isLoading={isLoading}
            isError={isError}
            onRetry={() => refetch()}
            onSelect={(doc) => navigate(`/chat?doc=${encodeURIComponent(doc.id)}`)}
            onDelete={(id) => del.mutate(id)}
            deletePending={del.isPending}
            onCancel={(id) => cancel.mutate(id)}
            cancelPending={cancel.isPending}
            onRetryDoc={(id) => retryDoc.mutate(id)}
            retryPending={retryDoc.isPending}
            onUploadVersion={(id, file) => uploadVersion.mutateAsync({ id, file })}
          />
        </CardBody>
      </Card>
    </div>
  );
}
