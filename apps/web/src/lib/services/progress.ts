import { apiFetch } from '@/lib/api';

export interface CourseProgress {
  courseId: string;
  percent: number;
  status: string;
  lessonCount: number;
  completedCount: number;
  updatedAt: string;
  completedLessonIds: string[];
}

export interface Badge {
  id: string;
  slug: string;
  name: string;
  description: string;
  icon: string;
}

export interface UserBadge {
  id: string;
  badge: Badge;
  earnedAt: string;
  contextId: string | null;
}

export interface ProgressUpdateResult {
  lessonProgress: {
    lessonId: string;
    status: 'not_started' | 'in_progress' | 'completed';
    lastScore: number | null;
  };
  courseProgress: CourseProgress;
  newBadges: Badge[];
}

function mapProgress(raw: Record<string, unknown>): CourseProgress {
  return {
    courseId: raw.course_id as string,
    percent: raw.percent as number,
    status: raw.status as string,
    lessonCount: raw.lesson_count as number,
    completedCount: raw.completed_count as number,
    updatedAt: raw.updated_at as string,
    completedLessonIds: (raw.completed_lesson_ids as string[]) ?? [],
  };
}

function mapBadge(raw: Record<string, unknown>): Badge {
  return {
    id: raw.id as string,
    slug: raw.slug as string,
    name: raw.name as string,
    description: raw.description as string,
    icon: raw.icon as string,
  };
}

export async function getCourseProgress(
  courseId: string,
  accessToken?: string
): Promise<CourseProgress> {
  const raw = await apiFetch<Record<string, unknown>>(`/progress/${courseId}`, { accessToken });
  return mapProgress(raw);
}

export async function markLessonComplete(
  lessonId: string,
  courseId: string,
  accessToken?: string
): Promise<ProgressUpdateResult> {
  const raw = await apiFetch<Record<string, unknown>>('/progress/update', {
    method: 'POST',
    body: { lesson_id: lessonId, course_id: courseId, status: 'completed' },
    accessToken,
  });

  const lp = raw.lesson_progress as Record<string, unknown>;
  const cp = raw.course_progress as Record<string, unknown>;
  const nb = (raw.new_badges as Record<string, unknown>[]) ?? [];

  return {
    lessonProgress: {
      lessonId: lp.lesson_id as string,
      status: lp.status as 'not_started' | 'in_progress' | 'completed',
      lastScore: lp.last_score as number | null,
    },
    courseProgress: mapProgress(cp),
    newBadges: nb.map(mapBadge),
  };
}

export async function getUserBadges(accessToken?: string): Promise<UserBadge[]> {
  const raw = await apiFetch<Record<string, unknown>[]>('/badges/user', { accessToken });
  return raw.map((item) => ({
    id: item.id as string,
    badge: mapBadge(item.badge as Record<string, unknown>),
    earnedAt: item.earned_at as string,
    contextId: item.context_id as string | null,
  }));
}
