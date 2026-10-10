/**
 * Course management is restricted server-side to admins and instructors
 * (PATCH/DELETE /courses). The UI must agree, or students are offered actions
 * that always fail with 403.
 */
import { canManageCourses } from '@/lib/auth/roles';

describe('canManageCourses', () => {
  it.each(['admin', 'instructor'])('allows %s', (role) => {
    expect(canManageCourses(role)).toBe(true);
  });

  it('denies students', () => {
    expect(canManageCourses('student')).toBe(false);
  });

  it('denies a missing or unknown role', () => {
    expect(canManageCourses(undefined)).toBe(false);
    expect(canManageCourses('')).toBe(false);
    expect(canManageCourses('superuser')).toBe(false);
  });
});
