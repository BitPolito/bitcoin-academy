/**
 * A READY document whose QVAC ingest did not complete is still searchable by
 * keyword, but the workspace must say that semantic search is unavailable.
 */
import '@testing-library/jest-dom';
import { render, screen } from '@testing-library/react';
import CourseWorkspacePage from '../../src/app/courses/[courseId]/page';

jest.mock('next/navigation', () => ({
  useParams: () => ({ courseId: 'course-1' }),
  useRouter: () => ({ push: jest.fn() }),
}));

jest.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { accessToken: 'token-1', role: 'student' } }, status: 'authenticated' }),
}));

jest.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast: jest.fn() }) }));

jest.mock('@/components/documents/DocumentProcessingPanel', () => ({
  DocumentProcessingPanel: () => null,
}));

jest.mock('@/lib/services/courses', () => ({
  getCourse: jest.fn(async () => ({ id: 'course-1', title: 'Bitcoin Basics' })),
  updateCourse: jest.fn(),
  deleteCourse: jest.fn(),
}));

jest.mock('@/lib/api/documents', () => ({
  getDocumentListRows: jest.fn(),
  deleteDocument: jest.fn(),
  reindexCourse: jest.fn(),
}));

import { getDocumentListRows } from '@/lib/api/documents';

const mockGetDocs = getDocumentListRows as jest.Mock;

function row(indexingStatus: string | null) {
  return {
    id: 'doc-1',
    courseId: 'course-1',
    filename: 'notes.pdf',
    fileType: 'PDF',
    size: 1024,
    status: 'ready',
    processingStage: 'done',
    isTerminal: true,
    errorMessage: null,
    indexingStatus,
    documentType: 'lecture',
    createdAt: '2026-10-26T00:00:00Z',
    updatedAt: '2026-10-26T00:00:00Z',
  };
}

it.each([
  ['qvac_failed', /Semantic indexing failed/],
  ['qvac_pending', /Semantic index pending/],
])('warns about a %s dense index on a ready document', async (status, text) => {
  mockGetDocs.mockResolvedValue([row(status)]);
  render(<CourseWorkspacePage />);
  expect(await screen.findByRole('status')).toHaveTextContent(text);
});

it('shows no warning for an indexed document', async () => {
  mockGetDocs.mockResolvedValue([row('indexed')]);
  render(<CourseWorkspacePage />);
  expect((await screen.findAllByText('notes.pdf')).length).toBeGreaterThan(0);
  expect(screen.queryByText(/Semantic index/)).not.toBeInTheDocument();
});
