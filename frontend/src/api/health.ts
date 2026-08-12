import { apiFetch } from './client';
import type { BackendStatus, HealthResponse } from '@/types/api';

/** GET /health */
export const getHealth = (): Promise<HealthResponse> => apiFetch<HealthResponse>('/health');

/** GET /config/backends */
export const getBackends = (): Promise<BackendStatus> =>
  apiFetch<BackendStatus>('/config/backends');
