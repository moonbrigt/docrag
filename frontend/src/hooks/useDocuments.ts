import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  cancelDocument,
  deleteDocument,
  getDocumentAcl,
  listDocuments,
  retryDocument,
  updateDocumentAcl,
  uploadDocument,
  uploadDocumentVersion,
} from '@/api/documents';
import type { DocumentAcl, DocumentItem } from '@/types/api';

export const documentsKey = ['documents'] as const;
export const aclKey = (id: string) => ['acl', id] as const;

const PROCESSING = ['queued', 'parsing', 'chunking', 'embedding'];

export function useDocuments() {
  return useQuery<DocumentItem[]>({
    queryKey: documentsKey,
    queryFn: listDocuments,
    refetchInterval: (query) => {
      // 存在"处理中"文档时每 3s 轮询，否则不自动轮询
      const data = query.state.data;
      const processing = data?.some((d) => PROCESSING.includes(d.status));
      return processing ? 3000 : false;
    },
  });
}

export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => uploadDocument(file),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentsKey }),
  });
}

export function useDeleteDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => deleteDocument(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentsKey }),
  });
}

export function useCancelDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => cancelDocument(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentsKey }),
  });
}

export function useRetryDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => retryDocument(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentsKey }),
  });
}

export function useUploadDocumentVersion() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, file }: { id: string; file: File }) => uploadDocumentVersion(id, file),
    onSuccess: () => qc.invalidateQueries({ queryKey: documentsKey }),
  });
}

/** 单个文档 ACL（对话框打开时才请求） */
export function useDocumentAcl(id: string | null) {
  return useQuery<DocumentAcl>({
    queryKey: aclKey(id ?? ''),
    queryFn: () => getDocumentAcl(id as string),
    enabled: !!id,
  });
}

export function useUpdateDocumentAcl() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, acl }: { id: string; acl: DocumentAcl }) => updateDocumentAcl(id, acl),
    onSuccess: (_data, { id }) => qc.invalidateQueries({ queryKey: aclKey(id) }),
  });
}
