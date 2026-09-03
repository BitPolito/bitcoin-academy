import { apiFetch } from '@/lib/api';
import type { CursorPage } from '@/lib/api/types';

export const COURSES_PAGE_SIZE = 20;

export interface Course {
  id: number;
  title: string;
  description?: string;
}

export interface Lesson {
  id: number;
  title: string;
  content?: string;
}

export interface CourseWithLessons extends Course {
  lessons: Lesson[];
}

export async function getCoursesPage(
  cursor?: string,
  limit = COURSES_PAGE_SIZE,
  accessToken?: string
): Promise<CursorPage<Course>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);
  return apiFetch<CursorPage<Course>>(`/courses?${params}`, {
    accessToken,
  });
}

export async function getCourses(accessToken?: string): Promise<Course[]> {
  const courses: Course[] = [];
  let cursor: string | undefined;
  do {
    const page = await getCoursesPage(cursor, 100, accessToken);
    courses.push(...page.items);
    cursor = page.next_cursor ?? undefined;
  } while (cursor);
  return courses;
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

export async function createCourse(title: string, description?: string): Promise<Course> {
  return apiFetch<Course>('/courses', {
    method: 'POST',
    body: { title, description },
  });
}

export async function updateCourse(
  courseId: string,
  title: string,
  description?: string,
  accessToken?: string
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
