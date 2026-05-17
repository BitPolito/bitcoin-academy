import { apiFetch } from '@/lib/api';
import type { ApiStudyRequest, ApiStudyResponse, StudyAction } from '@/lib/api/types';

export type { StudyAction, ApiStudyResponse as StudyResponse };

export async function sendStudyAction(
  courseId: string,
  action: StudyAction,
  query: string,
  accessToken?: string,
  ragOnly?: boolean,
): Promise<ApiStudyResponse> {
  const body: ApiStudyRequest = { action, query, ...(ragOnly ? { rag_only: true } : {}) };
  return apiFetch<ApiStudyResponse>(`/courses/${courseId}/study`, {
    method: 'POST',
    body,
    accessToken,
  });
}
