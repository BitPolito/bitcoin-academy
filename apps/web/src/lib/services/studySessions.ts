import { apiFetch } from '@/lib/api';
import type {
  ApiStudySessionDetailOut,
  ApiStudySessionOut,
  ApiStudyTurnOut,
  ApiTurnCitationOut,
} from '@/lib/api/types';

export type { ApiStudySessionOut as StudySession, ApiStudySessionDetailOut as StudySessionDetail };

export async function createStudySession(
  courseId: string,
  title?: string,
  accessToken?: string,
): Promise<ApiStudySessionOut> {
  return apiFetch<ApiStudySessionOut>(`/courses/${courseId}/sessions`, {
    method: 'POST',
    body: { title },
    accessToken,
  });
}

export async function listStudySessions(
  courseId: string,
  accessToken?: string,
): Promise<ApiStudySessionOut[]> {
  return apiFetch<ApiStudySessionOut[]>(`/courses/${courseId}/sessions`, {
    accessToken,
  });
}

export async function getStudySession(
  courseId: string,
  sessionId: string,
  accessToken?: string,
): Promise<ApiStudySessionDetailOut> {
  return apiFetch<ApiStudySessionDetailOut>(`/courses/${courseId}/sessions/${sessionId}`, {
    accessToken,
  });
}

export async function deleteStudySession(
  courseId: string,
  sessionId: string,
  accessToken?: string,
): Promise<{ status: string }> {
  return apiFetch<{ status: string }>(`/courses/${courseId}/sessions/${sessionId}`, {
    method: 'DELETE',
    accessToken,
  });
}

export interface ImportTurnInput {
  action: string;
  query: string;
  answer: string;
  citations?: ApiTurnCitationOut[];
  duration_ms?: number | null;
  model_tier?: string | null;
}

/**
 * Imports one historical turn verbatim into a session — used only to migrate
 * pre-existing localStorage study history on first load (issue #136). The
 * live study dispatch endpoints persist turns themselves; this is not a
 * general-purpose turn-creation call.
 */
export async function importStudyTurn(
  courseId: string,
  sessionId: string,
  turn: ImportTurnInput,
  accessToken?: string,
): Promise<ApiStudyTurnOut> {
  return apiFetch<ApiStudyTurnOut>(`/courses/${courseId}/sessions/${sessionId}/turns`, {
    method: 'POST',
    body: { citations: [], ...turn },
    accessToken,
  });
}
