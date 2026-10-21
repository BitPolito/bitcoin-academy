/**
 * The document list auto-selects its first row when nothing is selected, but
 * must never override a row the user picked, including after the list is
 * refetched (polling, re-index, upload).
 */
import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import CourseWorkspacePage from '../../src/app/courses/[courseId]/page';

jest.mock('next/navigation', () => ({
  useParams: () => ({ courseId: 'course-1' }),
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('next-auth/react', () => ({
  useSession: () => ({
    data: { user: { accessToken: 'token-1', role: 'student' } },
    status: 'authenticated',
  }),
}));

jest.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast: jest.fn() }) }));

jest.mock('@/lib/services/courses', () => ({
  getCourse: jest.fn(async () => ({ id: 'course-1', title: 'Bitcoin Basics' })),
  updateCourse: jest.fn(),
  deleteCourse: jest.fn(),
}));

jest.mock('@/lib/api/documents', () => ({
  getDocumentListRows: jest.fn(),
  deleteDocument: jest.fn(),
  reindexCourse: jest.fn(async () => ({ enqueued: 2, skipped: 0 })),
}));

import { getDocumentListRows } from '@/lib/api/documents';

const mockGetDocs = getDocumentListRows as jest.Mock;

const row = (id: string, filename: string) => ({
  id,
  filename,
  status: 'ready',
  documentType: 'lecture',
  size: 1024,
});

beforeEach(() => {
  jest.clearAllMocks();
  mockGetDocs.mockResolvedValue([row('doc-a', 'alpha.pdf'), row('doc-b', 'beta.pdf')]);
});

const detailHeading = () => screen.getByRole('heading', { level: 3 });

it('selects the first document on load', async () => {
  render(<CourseWorkspacePage />);
  await waitFor(() => expect(detailHeading()).toHaveTextContent('alpha.pdf'));
  expect(mockGetDocs).toHaveBeenCalledTimes(1);
});

it('keeps the user selection when the list is refetched', async () => {
  render(<CourseWorkspacePage />);
  await waitFor(() => expect(detailHeading()).toHaveTextContent('alpha.pdf'));

  fireEvent.click(screen.getByText('beta.pdf'));
  expect(detailHeading()).toHaveTextContent('beta.pdf');
  // Selecting a row must not trigger a refetch.
  expect(mockGetDocs).toHaveBeenCalledTimes(1);

  fireEvent.click(screen.getByText('↺ Reindex all'));
  await waitFor(() => expect(mockGetDocs).toHaveBeenCalledTimes(2));
  await waitFor(() => expect(detailHeading()).toHaveTextContent('beta.pdf'));
});
