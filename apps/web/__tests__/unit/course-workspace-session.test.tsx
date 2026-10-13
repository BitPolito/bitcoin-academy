/**
 * On a reload, useSession() is still loading on the first render, so the
 * access token is undefined. The workspace used to fetch immediately, get a
 * 401, and keep showing "Missing authentication token" even after the session
 * resolved and the retry succeeded.
 */
import '@testing-library/jest-dom';
import { render, screen, waitFor } from '@testing-library/react';
import CourseWorkspacePage from '../../src/app/courses/[courseId]/page';

jest.mock('next/navigation', () => ({
  useParams: () => ({ courseId: 'course-1' }),
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('next-auth/react', () => ({ useSession: jest.fn() }));

jest.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast: jest.fn() }) }));

jest.mock('@/lib/services/courses', () => ({
  getCourse: jest.fn(),
  updateCourse: jest.fn(),
  deleteCourse: jest.fn(),
}));

jest.mock('@/lib/api/documents', () => ({
  getDocumentListRows: jest.fn(),
  deleteDocument: jest.fn(),
  reindexCourse: jest.fn(),
}));

import { useSession } from 'next-auth/react';
import { getCourse } from '@/lib/services/courses';
import { getDocumentListRows } from '@/lib/api/documents';

const mockUseSession = useSession as jest.Mock;
const mockGetCourse = getCourse as jest.Mock;
const mockGetDocs = getDocumentListRows as jest.Mock;

beforeEach(() => {
  jest.clearAllMocks();
  // Mirror the backend: every course endpoint requires a token.
  mockGetCourse.mockImplementation(async (_id: string, token?: string) => {
    if (!token) throw new Error('Missing authentication token');
    return { id: 'course-1', title: 'Bitcoin Basics' };
  });
  mockGetDocs.mockImplementation(async (_id: string, token?: string) => {
    if (!token) throw new Error('Missing authentication token');
    return [];
  });
});

it('waits for the session instead of failing with a stale 401', async () => {
  mockUseSession.mockReturnValue({ data: null, status: 'loading' });
  const { rerender } = render(<CourseWorkspacePage />);

  mockUseSession.mockReturnValue({
    data: { user: { accessToken: 'token-1', role: 'student' } },
    status: 'authenticated',
  });
  rerender(<CourseWorkspacePage />);

  expect((await screen.findAllByText('Bitcoin Basics')).length).toBeGreaterThan(0);
  expect(screen.queryByText(/missing authentication token/i)).not.toBeInTheDocument();
  await waitFor(() => expect(mockGetDocs).toHaveBeenCalledWith('course-1', 'token-1'));
  expect(mockGetCourse).not.toHaveBeenCalledWith('course-1', undefined);
  expect(mockGetDocs).not.toHaveBeenCalledWith('course-1', undefined);
});
