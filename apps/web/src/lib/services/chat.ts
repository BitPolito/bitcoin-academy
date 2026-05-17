import { apiFetch, API_BASE_URL } from '@/lib/api';

export interface Citation {
  snippet: string;
  score: number;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  retrievalUsed: boolean;
}

export interface HistoryEntry {
  role: 'user' | 'assistant';
  content: string;
}

export async function submitFeedback(
  courseId: string,
  sessionId: string,
  question: string,
  answer: string,
  rating: 1 | -1,
  accessToken?: string,
  comment?: string,
): Promise<void> {
  await apiFetch<Record<string, unknown>>(`/courses/${courseId}/chat/feedback`, {
    method: 'POST',
    body: { session_id: sessionId, question, answer, rating, comment },
    accessToken,
  });
}

export async function sendChatMessageStream(
  courseId: string,
  message: string,
  onToken: (token: string) => void,
  onCitations: (citations: Citation[]) => void,
  accessToken?: string,
  history?: HistoryEntry[],
): Promise<void> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  if (accessToken) headers['Authorization'] = `Bearer ${accessToken}`;

  const response = await fetch(`${API_BASE_URL}/courses/${courseId}/chat/stream`, {
    method: 'POST',
    headers,
    body: JSON.stringify({ message, history: history ?? [] }),
  });

  if (!response.ok || !response.body) {
    throw new Error(`Stream request failed (${response.status})`);
  }

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
      if (payload.startsWith('[CITATIONS]')) {
        try {
          onCitations(JSON.parse(payload.slice('[CITATIONS]'.length)) as Citation[]);
        } catch { /* ignore */ }
        continue;
      }
      try {
        onToken(JSON.parse(payload) as string);
      } catch {
        onToken(payload);
      }
    }
  }
}

export async function sendChatMessage(
  courseId: string,
  message: string,
  accessToken?: string,
  history?: HistoryEntry[],
): Promise<ChatResponse> {
  const raw = await apiFetch<Record<string, unknown>>(`/courses/${courseId}/chat`, {
    method: 'POST',
    body: { message, history: history ?? [] },
    accessToken,
  });
  return {
    answer: raw.answer as string,
    citations: (raw.citations as Citation[]) ?? [],
    retrievalUsed: raw.retrieval_used as boolean,
  };
}
