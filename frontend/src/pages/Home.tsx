import { MessageSquare } from 'lucide-react';
import { UploadDropzone } from '@/components/common/UploadDropzone';
import { SystemStatus } from '@/components/common/SystemStatus';
import { RecentDocs } from '@/components/common/RecentDocs';
import { RecentChats } from '@/components/common/RecentChats';
import { useDocuments } from '@/hooks/useDocuments';
import { Card, CardHeader, CardTitle, CardBody } from '@/components/ui/Card';

export function Home() {
  const { data: documents = [] } = useDocuments();

  return (
    <div className="mx-auto w-full max-w-[var(--container-max)] space-y-6 px-4 py-6 md:px-6">
      <div>
        <h1 className="text-2xl font-announce text-fg">概览</h1>
        <p className="mt-1 text-sm text-muted">上传 PDF，构建可精准溯源的私有知识库。</p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle>上传文档</CardTitle>
            </CardHeader>
            <CardBody>
              <UploadDropzone />
            </CardBody>
          </Card>
          <section>
            <h2 className="mb-3 text-md font-emphasize text-fg">最近文档</h2>
            <RecentDocs documents={documents} />
          </section>
        </div>
        <div className="space-y-6">
          <SystemStatus documents={documents} />
          <section>
            <h2 className="mb-3 flex items-center gap-2 text-md font-emphasize text-fg">
              <MessageSquare size={16} className="text-meta" />
              最近问答
            </h2>
            <RecentChats />
          </section>
        </div>
      </div>
    </div>
  );
}
