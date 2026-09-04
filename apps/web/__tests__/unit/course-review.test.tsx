import '@testing-library/jest-dom';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useSession } from 'next-auth/react';
import { useParams } from 'next/navigation';

jest.mock('next-auth/react', () => ({ useSession: jest.fn() }));
jest.mock('next/navigation', () => ({
  useParams: jest.fn(),
  useRouter: () => ({ push: jest.fn() }),
}));
jest.mock('@/components/study/SplitPane', () => ({
  SplitPane: ({ left, right }: { left: React.ReactNode; right: React.ReactNode }) => (
    <div>{left}{right}</div>
  ),
}));
const showToast = jest.fn();
jest.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast }) }));
jest.mock('@/lib/services/courses', () => ({ getCourse: jest.fn() }));
jest.mock('@/lib/services/chapterTests', () => ({ generateChapterTest: jest.fn() }));
jest.mock('@/lib/services/courseBuilder', () => ({
  approveLesson: jest.fn(),
  editOutline: jest.fn(),
  generateContent: jest.fn(),
  generateOutline: jest.fn(),
  getGenerationRun: jest.fn(),
  getLessonContent: jest.fn(),
  getOutline: jest.fn(),
  patchLesson: jest.fn(),
  publishCourse: jest.fn(),
}));

import { getCourse } from '@/lib/services/courses';
import {
  editOutline,
  getLessonContent,
  getOutline,
  publishCourse,
} from '@/lib/services/courseBuilder';
import CourseReviewPage from '@/app/courses/[courseId]/review/page';

const outline = {
  course_id: 'course-1',
  is_stale: true,
  stale_reason: 'A source document changed.',
  generation_run: {
    id: 'run-1', course_id: 'course-1', status: 'done',
    prompt_version: 'outline-v1', created_at: '2026-09-04T10:00:00Z',
  },
  chapters: [{
    id: 'chapter-1', title: 'Foundations', order_index: 0, status: 'draft',
    is_human_modified: true, is_stale: true, stale_reason: 'Source changed',
    lessons: [{
      id: 'lesson-1', title: 'What is Bitcoin?', order_index: 0, status: 'draft',
      source_refs: ['chunk-1'], is_human_modified: false, is_stale: true,
      stale_reason: 'Source changed',
      sources: [{ chunk_id: 'chunk-1', document_id: 'doc-1' }],
    }],
  }],
};

describe('course review page', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (useParams as jest.Mock).mockReturnValue({ courseId: 'course-1' });
    (useSession as jest.Mock).mockReturnValue({ data: { user: { accessToken: 'token' } } });
    (getCourse as jest.Mock).mockResolvedValue({ id: 'course-1', title: 'Bitcoin' });
    (getOutline as jest.Mock).mockResolvedValue(outline);
    (editOutline as jest.Mock).mockResolvedValue(outline);
    (publishCourse as jest.Mock).mockResolvedValue({
      published_chapters: 0, published_lessons: 0, skipped_chapters: 1,
    });
    (getLessonContent as jest.Mock).mockResolvedValue({
      id: 'lesson-1', title: 'What is Bitcoin?', content: 'Reviewed content',
      description: 'Introduction', status: 'draft', source_refs: ['chunk-1'],
      review_issues: [], quiz: null,
    });
  });

  it('shows staleness, generation provenance, and source links', async () => {
    render(<CourseReviewPage />);

    expect(await screen.findByText('Bitcoin — Course Review')).toBeInTheDocument();
    expect(screen.getByText(/Outline needs review/)).toBeInTheDocument();
    expect(screen.getByText(/outline-v1/)).toBeInTheDocument();
    const source = screen.getByRole('link', { name: /What is Bitcoin\?: chunk-1/ });
    expect(source).toHaveAttribute(
      'href',
      '/courses/course-1/documents/doc-1/preview?chunk=chunk-1'
    );
  });

  it('loads a lesson, accepts stale content, and reports blocked publication', async () => {
    render(<CourseReviewPage />);
    fireEvent.click(await screen.findByRole('button', { name: 'What is Bitcoin?' }));
    expect(await screen.findByDisplayValue('Reviewed content')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Accept' }));
    await waitFor(() => expect(editOutline).toHaveBeenCalledWith(
      'course-1', { action: 'accept_stale', lesson_id: 'lesson-1' }, 'token'
    ));

    fireEvent.click(screen.getByRole('button', { name: 'Publish course' }));
    await waitFor(() => expect(publishCourse).toHaveBeenCalledWith('course-1', 'token'));
    expect(showToast).toHaveBeenCalledWith(expect.stringContaining('1 pending review'), 'warn');
  });
});
