import { apiFetch } from './client';
import type { EvaluationReport, EvaluationRunConfig } from '@/types/api';

// =============================================================================
// POST /evaluation/run —— 运行评测集，返回引用准确率 / 召回@K / Hit Rate / MRR。
// profile: 'public_nist'（真实公开 PDF 语料） | 'synthetic_smoke'（内置冒烟集）。
// 请求体同时携带顶层 profile 与 config.profile（兼容新旧两种后端读取方式，
// pydantic 默认忽略多余字段；后端以 config 为准时回退默认 NIST profile）。
// =============================================================================
export const runEvaluation = (config?: EvaluationRunConfig): Promise<EvaluationReport> =>
  apiFetch<EvaluationReport>('/evaluation/run', {
    method: 'POST',
    body: {
      ...(config?.profile ? { profile: config.profile, config: { profile: config.profile } } : {}),
      ...(config?.dataset ? { dataset: config.dataset } : {}),
    },
  });
