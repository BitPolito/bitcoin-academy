// Mirrors the backend reviewer guard on PATCH/DELETE /courses
// (CurrentUser(roles=[ADMIN, INSTRUCTOR]) in services/ai/app/api/courses_api.py).
const COURSE_MANAGER_ROLES = new Set(['admin', 'instructor']);

export function canManageCourses(role?: string | null): boolean {
  return !!role && COURSE_MANAGER_ROLES.has(role);
}
