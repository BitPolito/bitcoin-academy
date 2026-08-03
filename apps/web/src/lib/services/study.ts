import { apiFetch, API_BASE_URL } from '@/lib/api';
import type { ApiCitationOut, ApiStudyRequest, ApiStudyResponse, StudyAction } from '@/lib/api/types';

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

const CITATIONS_SENTINEL = '\x00CITATIONS\x00';

/**
 * Streams a study action via SSE from /courses/{courseId}/study/stream.
 *
 * Tokens are delivered to onToken as they arrive. After the last token the
 * backend emits a citations sentinel; onCitations is called with the parsed
 * citation array. The function resolves when the [DONE] marker is received.
 */
export async function sendStudyActionStream(
  courseId: string,
  action: StudyAction,
  query: string,
  onToken: (token: string) => void,
  onCitations: (citations: ApiCitationOut[]) => void,
  accessToken?: string,
  ragOnly?: boolean,
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

  const body: ApiStudyRequest = { action, query, ...(ragOnly ? { rag_only: true } : {}) };

  const response = await fetch(`${API_BASE_URL}/courses/${courseId}/study/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const msg = response.status === 429 ? 'Troppe richieste — riprova tra qualche secondo.' : `Stream request failed (${response.status})`;
    throw new Error(msg);
  }
  if (!response.body) throw new Error('Stream response body is null');

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const payload = line.slice(6);
      if (payload === '[DONE]') return;

      let token: string;
      try {
        token = JSON.parse(payload) as string;
      } catch {
        token = payload;
      }

      if (token.startsWith(CITATIONS_SENTINEL)) {
        try {
          onCitations(JSON.parse(token.slice(CITATIONS_SENTINEL.length)) as ApiCitationOut[]);
        } catch { /* ignore malformed citations */ }
        continue;
      }

      onToken(token);
    }
  }
}
