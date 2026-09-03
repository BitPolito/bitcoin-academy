import { apiFetch } from '@/lib/api';
import type { ApiCourse, ApiLesson, CreateCourseRequest, CursorPage } from './types';

export async function fetchCourses(
  cursor?: string,
  limit = 20,
  accessToken?: string
): Promise<CursorPage<ApiCourse>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set('cursor', cursor);
  return apiFetch<CursorPage<ApiCourse>>(`/courses?${params}`, {
    accessToken,
  });
}

export async function fetchCourse(courseId: string, accessToken?: string): Promise<ApiCourse> {
  return apiFetch<ApiCourse>(`/courses/${courseId}`, { accessToken });
}

export async function fetchCourseLessons(
  courseId: string,
  accessToken?: string
): Promise<ApiLesson[]> {
  return apiFetch<ApiLesson[]>(`/courses/${courseId}/lessons`, { accessToken });
}

export async function createCourse(
  data: CreateCourseRequest,
  accessToken?: string
): Promise<ApiCourse> {
  return apiFetch<ApiCourse>('/courses', {
    method: 'POST',
    body: data,
    accessToken,
  });
}
