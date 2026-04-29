import { apiFetch } from '@/lib/api';

export interface Citation {
  snippet: string;
  score: number;
}

export interface ChatResponse {
  answer: string;
  citations: Citation[];
  retrievalUsed: boolean;
}

export async function sendChatMessage(
  courseId: string,
  message: string,
  accessToken?: string
): Promise<ChatResponse> {
  const raw = await apiFetch<Record<string, unknown>>(`/courses/${courseId}/chat`, {
    method: 'POST',
    body: { message },
    accessToken,
  });
  return {
    answer: raw.answer as string,
    citations: (raw.citations as Citation[]) ?? [],
    retrievalUsed: raw.retrieval_used as boolean,
  };
}
