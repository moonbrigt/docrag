import { apiFetch } from './client';

export interface HistogramSnapshot {
  count: number;
  avg_ms: number;
  p50_ms: number;
  p95_ms: number;
  min_ms: number;
  max_ms: number;
}

export interface MetricsResponse {
  counters: Record<string, number>;
  histograms: Record<string, HistogramSnapshot>;
  generated_at: number;
}

/** GET /metrics */
export const getMetrics = (): Promise<MetricsResponse> =>
  apiFetch<MetricsResponse>('/metrics');
