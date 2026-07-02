import { apiFetch } from '@/lib/api';

export interface ChapterTestOption {
  id: string;
  label: string;
}

export interface ChapterTestQuestion {
  id: string;
  prompt: string;
  order_index: number;
  options: ChapterTestOption[];
}

export interface ChapterTest {
  id: string;
  chapter_id: string;
  title: string;
  quiz_id: string;
  passing_score: number;
  questions: ChapterTestQuestion[];
}

export interface QuizAttemptCorrection {
  question_id: string;
  correct_option_id: string | null;
  selected_option_id: string | null;
  is_correct: boolean;
}

export interface QuizAttemptResult {
  attempt_id: string;
  score_pct: number;
  passed: boolean;
  correct_count: number;
  total_count: number;
  corrections: QuizAttemptCorrection[];
}

export async function generateChapterTest(chapterId: string, accessToken?: string): Promise<ChapterTest> {
  return apiFetch<ChapterTest>(`/chapters/${chapterId}/test/generate`, {
    method: 'POST',
    accessToken,
  });
}

export async function getChapterTest(chapterId: string, accessToken?: string): Promise<ChapterTest> {
  return apiFetch<ChapterTest>(`/chapters/${chapterId}/test`, { accessToken });
}

export async function submitQuizAttempt(
  quizId: string,
  answers: Record<string, string>,
  accessToken?: string
): Promise<QuizAttemptResult> {
  return apiFetch<QuizAttemptResult>(`/quizzes/${quizId}/attempts`, {
    method: 'POST',
    body: { answers },
    accessToken,
  });
}
