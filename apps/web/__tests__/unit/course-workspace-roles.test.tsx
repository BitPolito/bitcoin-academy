/**
 * Uploading, re-indexing and deleting course material is instructor/admin only
 * on the backend (documents_api.py, courses_api.py), so the workspace must not
 * offer those actions to students.
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
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

function renderAs(role: string) {
  mockUseSession.mockReturnValue({
    data: { user: { accessToken: 'token-1', role } },
    status: 'authenticated',
  });
  return render(<CourseWorkspacePage />);
}

beforeEach(() => {
  jest.clearAllMocks();
  (getCourse as jest.Mock).mockResolvedValue({ id: 'course-1', title: 'Bitcoin Basics' });
  (getDocumentListRows as jest.Mock).mockResolvedValue([
    {
      id: 'doc-1',
      courseId: 'course-1',
      filename: 'whitepaper.pdf',
      fileType: 'pdf',
      size: 1024,
      status: 'ready',
      processingStage: 'done',
      isTerminal: true,
      errorMessage: null,
      documentType: 'lecture',
      createdAt: '2026-10-20T00:00:00Z',
      updatedAt: '2026-10-20T00:00:00Z',
    },
  ]);
});

it('hides upload, reindex and delete from students but keeps the material readable', async () => {
  renderAs('student');

  expect((await screen.findAllByText('whitepaper.pdf')).length).toBeGreaterThan(0);
  expect(screen.getByTitle('Open preview')).toBeInTheDocument();
  expect(screen.queryByText(/upload · drop or click/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/reindex all/i)).not.toBeInTheDocument();
  expect(screen.queryByTitle('Delete document')).not.toBeInTheDocument();
});

it.each(['instructor', 'admin'])('offers upload, reindex and delete to %s', async (role) => {
  renderAs(role);

  expect((await screen.findAllByText('whitepaper.pdf')).length).toBeGreaterThan(0);
  expect(screen.getByText(/upload · drop or click/i)).toBeInTheDocument();
  expect(screen.getByText(/reindex all/i)).toBeInTheDocument();
  expect(screen.getByTitle('Delete document')).toBeInTheDocument();
});
