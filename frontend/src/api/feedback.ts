import { apiFetch } from './client';
import type { FeedbackRequest } from '@/types/api';

/** POST /feedback —— 提交答案反馈（trace_id + 有用性 + 问题类型 + 可选评论） */
export const submitFeedback = (body: FeedbackRequest): Promise<unknown> =>
  apiFetch<unknown>('/feedback', { method: 'POST', body });
