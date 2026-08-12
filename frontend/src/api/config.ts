import { apiFetch } from './client';
import type { RuntimeConfigResponse, SettingsUpdatePayload } from '@/types/api';

/** GET /config/settings —— 当前生效的运行时配置（api_key 只回传是否已设置） */
export const getRuntimeConfig = (): Promise<RuntimeConfigResponse> =>
  apiFetch<RuntimeConfigResponse>('/config/settings');

/** PUT /config/settings —— 写入运行时覆盖（持久化 + 即时生效，无需重启） */
export const updateRuntimeConfig = (payload: SettingsUpdatePayload): Promise<RuntimeConfigResponse> =>
  apiFetch<RuntimeConfigResponse>('/config/settings', { method: 'PUT', body: payload });
