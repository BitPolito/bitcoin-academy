import { apiFetch } from '@/lib/api';
import type { ApiCourse, ApiLesson, CreateCourseRequest } from './types';

export async function fetchCourses(
  skip = 0,
  limit = 100,
  accessToken?: string,
): Promise<ApiCourse[]> {
  return apiFetch<ApiCourse[]>(`/courses?skip=${skip}&limit=${limit}`, {
    accessToken,
  });
}

export async function fetchCourse(
  courseId: string,
  accessToken?: string,
): Promise<ApiCourse> {
  return apiFetch<ApiCourse>(`/courses/${courseId}`, { accessToken });
}

export async function fetchCourseLessons(
  courseId: string,
  accessToken?: string,
): Promise<ApiLesson[]> {
  return apiFetch<ApiLesson[]>(`/courses/${courseId}/lessons`, { accessToken });
}

export async function createCourse(
  data: CreateCourseRequest,
  accessToken?: string,
): Promise<ApiCourse> {
  return apiFetch<ApiCourse>('/courses', {
    method: 'POST',
    body: data,
    accessToken,
  });
}
