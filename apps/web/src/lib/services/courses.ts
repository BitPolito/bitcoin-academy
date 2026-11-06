import { apiFetch } from '@/lib/api';

export const DEFAULT_COURSES_PAGE_SIZE = 20;

export interface Course {
  id: number;
  title: string;
  description?: string;
}

// Cursor-paginated envelope from GET /api/courses — see issue #73.
// next_cursor is an opaque token; callers must not parse or construct it.
export interface CoursePage {
  items: Course[];
  nextCursor: string | null;
  hasMore: boolean;
}

export interface Lesson {
  id: number;
  title: string;
  content?: string;
}

export interface CourseWithLessons extends Course {
  lessons: Lesson[];
}

export async function getCourses(
  cursor?: string | null,
  limit = DEFAULT_COURSES_PAGE_SIZE,
  accessToken?: string,
): Promise<CoursePage> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);
  const page = await apiFetch<{ items: Course[]; next_cursor: string | null; has_more: boolean }>(
    `/courses?${params.toString()}`,
    { accessToken },
  );
  return { items: page.items, nextCursor: page.next_cursor, hasMore: page.has_more };
}

export async function getCourse(courseId: string, accessToken?: string): Promise<Course> {
  return apiFetch<Course>(`/courses/${courseId}`, { accessToken });
}

export async function getCourseLessons(courseId: string, accessToken?: string): Promise<Lesson[]> {
  return apiFetch<Lesson[]>(`/courses/${courseId}/lessons`, { accessToken });
}

export async function getLesson(lessonId: string, accessToken?: string): Promise<Lesson> {
  return apiFetch<Lesson>(`/lessons/${lessonId}`, { accessToken });
}

export async function createCourse(
  title: string,
  description?: string,
  accessToken?: string,
): Promise<Course> {
  return apiFetch<Course>('/courses', {
    method: 'POST',
    body: { title, description },
    accessToken,
  });
}

export async function updateCourse(
  courseId: string,
  title: string,
  description?: string,
  accessToken?: string,
): Promise<Course> {
  return apiFetch<Course>(`/courses/${courseId}`, {
    method: 'PATCH',
    body: { title, description },
    accessToken,
  });
}

export async function deleteCourse(courseId: string, accessToken?: string): Promise<void> {
  await apiFetch<{ message: string }>(`/courses/${courseId}`, {
    method: 'DELETE',
    accessToken,
  });
}
