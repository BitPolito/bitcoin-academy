import { apiFetch } from '@/lib/api';

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

export async function getCourses(
  skip = 0,
  limit = 100,
  accessToken?: string
): Promise<Course[]> {
  return apiFetch<Course[]>(`/courses?skip=${skip}&limit=${limit}`, {
    accessToken,
  });
}

export async function getCourse(
  courseId: string,
  accessToken?: string
): Promise<Course> {
  return apiFetch<Course>(`/courses/${courseId}`, { accessToken });
}

export async function getCourseLessons(
  courseId: string,
  accessToken?: string
): Promise<Lesson[]> {
  return apiFetch<Lesson[]>(`/courses/${courseId}/lessons`, { accessToken });
}

export async function getLesson(
  lessonId: string,
  accessToken?: string
): Promise<Lesson> {
  return apiFetch<Lesson>(`/lessons/${lessonId}`, { accessToken });
}

export async function createCourse(
  title: string,
  description?: string,
): Promise<Course> {
  return apiFetch<Course>('/courses', {
    method: 'POST',
    body: { title, description },
  });
}
