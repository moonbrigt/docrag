// =============================================================================
// HTTP 请求封装（JSON API）。SSE 走 api/chat.ts。
// 所有路径基于 /api/v1；开发期由 Vite 代理到后端 8000。
// =============================================================================

export const API_BASE = '/api/v1';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

interface JsonOptions {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

export async function parseError(res: Response): Promise<string> {
  let msg = `请求失败（${res.status}）`;
  try {
    const body = (await res.json()) as { message?: string };
    if (body?.message) msg = body.message;
  } catch {
    /* 忽略非 JSON 响应体 */
  }
  return msg;
}

export async function apiFetch<T>(path: string, options: JsonOptions = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? 'GET',
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });

  if (!res.ok) {
    throw new ApiError(res.status, await parseError(res));
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** 提取后端错误信息（用于 catch 分支展示具体文案） */
export function extractErrorMessage(err: unknown, fallback = '操作失败'): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return fallback;
}
