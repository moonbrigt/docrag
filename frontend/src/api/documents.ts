import { API_BASE, ApiError, apiFetch, parseError } from './client';
import type {
  DocumentAcl,
  DocumentDetail,
  DocumentItem,
  UploadResponse,
} from '@/types/api';

/** POST /documents —— 上传 PDF，触发解析流水线（202 + document_id） */
export async function uploadDocument(file: File): Promise<UploadResponse> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/documents`, {
    method: 'POST',
    body: form, // 不手动设置 Content-Type，由浏览器生成 boundary
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  return (await res.json()) as UploadResponse;
}

/** GET /documents —— 文档列表 */
export const listDocuments = (): Promise<DocumentItem[]> =>
  fetch(`${API_BASE}/documents`).then(async (res) => {
    if (!res.ok) throw new ApiError(res.status, '获取文档列表失败');
    return (await res.json()) as DocumentItem[];
  });

/** GET /documents/{id} —— 文档详情 + 分块预览 */
export const getDocument = (id: string): Promise<DocumentDetail> =>
  fetch(`${API_BASE}/documents/${id}`).then(async (res) => {
    if (!res.ok) throw new ApiError(res.status, '获取文档详情失败');
    return (await res.json()) as DocumentDetail;
  });

/** DELETE /documents/{id} —— 删除文档（204） */
export async function deleteDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/${id}`, { method: 'DELETE' });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}

/** POST /documents/{id}/cancel —— 取消进行中的解析流水线 */
export async function cancelDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/${id}/cancel`, { method: 'POST' });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}

/** POST /documents/{id}/retry —— 重新处理 failed / warning / cancelled 文档 */
export async function retryDocument(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/documents/${id}/retry`, { method: 'POST' });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
}

/** POST /documents/{id}/versions —— 上传新版本替换当前内容（multipart） */
export async function uploadDocumentVersion(
  id: string,
  file: File,
): Promise<DocumentItem | undefined> {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}/documents/${id}/versions`, {
    method: 'POST',
    body: form,
  });
  if (!res.ok) throw new ApiError(res.status, await parseError(res));
  if (res.status === 204) return undefined;
  return (await res.json()) as DocumentItem;
}

/** GET /documents/{id}/acl —— 来源访问控制 */
export const getDocumentAcl = (id: string): Promise<DocumentAcl> =>
  apiFetch<DocumentAcl>(`/documents/${id}/acl`);

/** PUT /documents/{id}/acl —— 更新来源访问控制 */
export const updateDocumentAcl = (id: string, acl: DocumentAcl): Promise<DocumentAcl> =>
  apiFetch<DocumentAcl>(`/documents/${id}/acl`, { method: 'PUT', body: acl });

/** GET /documents/{id}/file —— 返回完整原始 PDF，供 pdfjs 按页渲染与 bbox 高亮。 */
export const getDocumentFileUrl = (id: string): string =>
  `${API_BASE}/documents/${id}/file`;
