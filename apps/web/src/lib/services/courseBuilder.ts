import { apiFetch } from '@/lib/api';

// ---------------------------------------------------------------------------
// Types — mirror services/ai/app/schemas/outline_schemas.py and content_api.py
// ---------------------------------------------------------------------------

export interface LessonDraft {
  id: string;
  title: string;
  description?: string;
  status?: string;
  order_index: number;
  source_refs: string[];
}

export interface ChapterDraft {
  id: string;
  title: string;
  description?: string;
  status?: string;
  order_index: number;
  lessons: LessonDraft[];
}

export interface OutlineResponse {
  course_id: string;
  run_id?: string;
  chapters: ChapterDraft[];
}

export interface GenerationRun {
  id: string;
  course_id: string;
  status: 'queued' | 'running' | 'done' | 'error';
  stage?: string;
  error_message?: string;
  prompt_version?: string;
  started_at?: string;
  finished_at?: string;
  created_at: string;
}

export interface LessonQuizOption {
  id: string;
  label: string;
}

export interface LessonQuizQuestion {
  id: string;
  prompt: string;
  order_index: number;
  options: LessonQuizOption[];
}

export interface LessonQuiz {
  id: string;
  title?: string;
  passing_score: number;
  questions: LessonQuizQuestion[];
}

export interface LessonContent {
  id: string;
  title: string;
  description?: string;
  content: string;
  status?: string;
  order_index: number;
  source_refs: string[];
  review_issues: string[];
  quiz?: LessonQuiz | null;
}

export interface PublishResult {
  published_chapters: number;
  published_lessons: number;
  skipped_chapters: number;
}

// ---------------------------------------------------------------------------
// Outline
// ---------------------------------------------------------------------------

export async function getOutline(courseId: string, accessToken?: string): Promise<OutlineResponse> {
  return apiFetch<OutlineResponse>(`/courses/${courseId}/outline`, { accessToken });
}

export async function generateOutline(
  courseId: string,
  accessToken?: string
): Promise<{ run_id: string; status: string }> {
  return apiFetch(`/courses/${courseId}/outline/generate`, {
    method: 'POST',
    body: {},
    accessToken,
  });
}

// ---------------------------------------------------------------------------
// Content generation
// ---------------------------------------------------------------------------

export async function generateContent(
  courseId: string,
  lessonIds?: string[],
  accessToken?: string
): Promise<{ run_id: string; status: string; draft_lessons: number }> {
  return apiFetch(`/courses/${courseId}/content/generate`, {
    method: 'POST',
    body: lessonIds ? { lesson_ids: lessonIds } : {},
    accessToken,
  });
}

export async function publishCourse(courseId: string, accessToken?: string): Promise<PublishResult> {
  return apiFetch<PublishResult>(`/courses/${courseId}/publish`, {
    method: 'POST',
    accessToken,
  });
}

export async function getGenerationRun(runId: string, accessToken?: string): Promise<GenerationRun> {
  return apiFetch<GenerationRun>(`/generation-runs/${runId}`, { accessToken });
}

// ---------------------------------------------------------------------------
// Lesson review
// ---------------------------------------------------------------------------

export async function getLessonContent(lessonId: string, accessToken?: string): Promise<LessonContent> {
  return apiFetch<LessonContent>(`/lessons/${lessonId}/content`, { accessToken });
}

export async function patchLesson(
  lessonId: string,
  data: { title?: string; description?: string; content?: string },
  accessToken?: string
): Promise<LessonContent> {
  return apiFetch<LessonContent>(`/lessons/${lessonId}`, {
    method: 'PATCH',
    body: data,
    accessToken,
  });
}

export async function approveLesson(
  lessonId: string,
  accessToken?: string
): Promise<{ id: string; status: string }> {
  return apiFetch(`/lessons/${lessonId}/approve`, {
    method: 'POST',
    accessToken,
  });
}
