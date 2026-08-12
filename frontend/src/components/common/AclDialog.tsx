import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';
import type { DocumentAcl, DocumentItem } from '@/types/api';
import { useDocumentAcl, useUpdateDocumentAcl } from '@/hooks/useDocuments';
import { extractErrorMessage } from '@/api/client';
import { AppDialog } from '@/components/ui/Dialog';
import { Button } from '@/components/ui/Button';
import { Input, Textarea } from '@/components/ui/Input';
import { Spinner } from '@/components/ui/Spinner';

// 来源 ACL 管理对话框：tenant_id / owner_user_id / groups（GET+PUT /documents/{id}/acl）。
// Esc / 遮罩关闭由 Radix Dialog 提供，保存成功后自动关闭。
export function AclDialog({
  doc,
  open,
  onOpenChange,
}: {
  doc: DocumentItem | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const id = open ? (doc?.id ?? null) : null;
  const { data, isLoading, isError } = useDocumentAcl(id);
  const update = useUpdateDocumentAcl();

  const [tenantId, setTenantId] = useState('default');
  const [ownerUserId, setOwnerUserId] = useState('demo');
  const [groupsText, setGroupsText] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setTenantId(data.tenant_id ?? '');
      setOwnerUserId(data.owner_user_id ?? '');
      setGroupsText((data.groups ?? []).join('\n'));
    }
  }, [data]);

  const submit = async () => {
    if (!id) return;
    setError(null);
    const acl: DocumentAcl = {
      tenant_id: tenantId.trim(),
      owner_user_id: ownerUserId.trim(),
      groups: groupsText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean),
    };
    try {
      await update.mutateAsync({ id, acl });
      onOpenChange(false);
    } catch (e) {
      setError(extractErrorMessage(e, '保存 ACL 失败'));
    }
  };

  return (
    <AppDialog
      open={open}
      onOpenChange={(o) => {
        if (!o) setError(null);
        onOpenChange(o);
      }}
      title="访问权限（ACL）"
      description={`配置「${doc?.filename ?? ''}」来源的可见范围，检索与回答将按此过滤。`}
      footer={
        <>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            取消
          </Button>
          <Button
            loading={update.isPending}
            disabled={isLoading || isError}
            onClick={submit}
          >
            保存
          </Button>
        </>
      }
    >
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Spinner size={24} />
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 text-sm text-danger">
          <LoaderCircle size={16} className="animate-spin" aria-hidden />
          无法读取该文档的 ACL，请稍后重试。
        </div>
      ) : (
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-xs text-meta caps-label" htmlFor="acl-tenant">
              Tenant
            </label>
            <Input
              id="acl-tenant"
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              placeholder="default"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-meta caps-label" htmlFor="acl-owner">
              Owner 用户
            </label>
            <Input
              id="acl-owner"
              value={ownerUserId}
              onChange={(e) => setOwnerUserId(e.target.value)}
              placeholder="demo"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs text-meta caps-label" htmlFor="acl-groups">
              可见组（每行一个）
            </label>
            <Textarea
              id="acl-groups"
              value={groupsText}
              onChange={(e) => setGroupsText(e.target.value)}
              rows={3}
              placeholder="group-a&#10;group-b"
              className="font-mono text-xs"
            />
          </div>
          {error && <p className="text-sm text-danger">{error}</p>}
        </div>
      )}
    </AppDialog>
  );
}
