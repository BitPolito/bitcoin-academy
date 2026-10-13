import '@testing-library/jest-dom';
import type { ReactNode } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useSession } from 'next-auth/react';
import { useParams } from 'next/navigation';

jest.mock('next-auth/react', () => ({ useSession: jest.fn() }));
jest.mock('next/navigation', () => ({
  useParams: jest.fn(),
  useRouter: () => ({ push: jest.fn() }),
}));
jest.mock('@/components/study/SplitPane', () => ({
  SplitPane: ({ left, right }: { left: ReactNode; right: ReactNode }) => (
    <div>{left}{right}</div>
  ),
}));
jest.mock('@/components/ui/Toast', () => ({
  useToast: () => ({ showToast: jest.fn() }),
}));
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

import CourseReviewPage from '@/app/courses/[courseId]/review/page';
import { getCourse } from '@/lib/services/courses';
import { editOutline, getOutline } from '@/lib/services/courseBuilder';

const lesson = (id: string, title: string, order_index: number) => ({
  id,
  title,
  order_index,
  status: 'draft',
  source_refs: [`source-${id}`],
  is_human_modified: false,
});

const outline = {
  course_id: 'course-1',
  chapters: [
    {
      id: 'chapter-1',
      title: 'Foundations',
      order_index: 0,
      status: 'draft',
      is_human_modified: false,
      lessons: [lesson('lesson-1', 'Money', 0), lesson('lesson-2', 'Bitcoin', 1)],
    },
    {
      id: 'chapter-2',
      title: 'Advanced',
      order_index: 1,
      status: 'draft',
      is_human_modified: false,
      lessons: [lesson('lesson-3', 'Mining', 0)],
    },
  ],
};

async function renderReview() {
  render(<CourseReviewPage />);
  await screen.findByText('Bitcoin Academy — Course Review');
}

async function expectAction(action: Record<string, unknown>) {
  await waitFor(() => expect(editOutline).toHaveBeenCalledWith('course-1', action, 'token'));
  await waitFor(() => expect(screen.getByRole('button', { name: '+ Add chapter' })).toBeEnabled());
}

describe('manual outline editing UI', () => {
  afterEach(() => jest.restoreAllMocks());

  beforeEach(() => {
    jest.clearAllMocks();
    (useParams as jest.Mock).mockReturnValue({ courseId: 'course-1' });
    (useSession as jest.Mock).mockReturnValue({ data: { user: { accessToken: 'token' } } });
    (getCourse as jest.Mock).mockResolvedValue({ id: 'course-1', title: 'Bitcoin Academy' });
    (getOutline as jest.Mock).mockResolvedValue(outline);
    (editOutline as jest.Mock).mockResolvedValue(outline);
  });

  it('creates and renames chapters and lessons', async () => {
    const prompt = jest.spyOn(window, 'prompt');
    prompt.mockReturnValueOnce('Manual chapter');
    await renderReview();

    fireEvent.click(screen.getByRole('button', { name: '+ Add chapter' }));
    await expectAction({ action: 'create_chapter', title: 'Manual chapter' });

    prompt.mockReturnValueOnce('Renamed chapter');
    fireEvent.click(screen.getAllByTitle('Rename chapter')[0]);
    await expectAction({
      action: 'rename_chapter', chapter_id: 'chapter-1', title: 'Renamed chapter',
    });

    prompt.mockReturnValueOnce('Manual lesson');
    fireEvent.click(screen.getAllByRole('button', { name: '+ Add lesson' })[0]);
    await expectAction({
      action: 'create_lesson', chapter_id: 'chapter-1', title: 'Manual lesson',
    });

    prompt.mockReturnValueOnce('Renamed lesson');
    fireEvent.click(screen.getAllByTitle('Rename lesson')[0]);
    await expectAction({
      action: 'rename_lesson', lesson_id: 'lesson-1', title: 'Renamed lesson',
    });
  });

  it('reorders chapters and lessons and moves lessons between chapters', async () => {
    jest.spyOn(window, 'prompt').mockReturnValue('Advanced');
    await renderReview();

    fireEvent.click(screen.getAllByTitle('Move chapter up')[1]);
    await expectAction({ action: 'reorder_chapters', ordered_ids: ['chapter-2', 'chapter-1'] });

    fireEvent.click(screen.getAllByTitle('Move lesson up')[1]);
    await expectAction({
      action: 'reorder_lessons', chapter_id: 'chapter-1',
      ordered_ids: ['lesson-2', 'lesson-1'],
    });

    fireEvent.click(screen.getAllByTitle('Move lesson to another chapter')[0]);
    await expectAction({
      action: 'move_lesson', lesson_id: 'lesson-1', target_chapter_id: 'chapter-2',
    });
  });

  it('merges and splits chapters only after explicit reviewer input', async () => {
    const confirm = jest.spyOn(window, 'confirm').mockReturnValue(true);
    jest.spyOn(window, 'prompt').mockReturnValue('Split chapter');
    await renderReview();

    fireEvent.click(screen.getAllByTitle('Merge into previous chapter')[1]);
    expect(confirm).toHaveBeenCalledWith('Merge “Advanced” into the previous chapter?');
    await expectAction({
      action: 'merge_chapters', chapter_id: 'chapter-2', target_chapter_id: 'chapter-1',
    });

    fireEvent.click(screen.getAllByTitle('Split chapter before this lesson')[1]);
    await expectAction({
      action: 'split_chapter', chapter_id: 'chapter-1', title: 'Split chapter',
      lesson_ids: ['lesson-2'],
    });
  });

  it('requires confirmation before deleting generated content', async () => {
    const confirm = jest.spyOn(window, 'confirm').mockReturnValue(false);
    await renderReview();

    fireEvent.click(screen.getAllByTitle('Delete chapter')[0]);
    fireEvent.click(screen.getAllByTitle('Delete lesson')[0]);
    expect(editOutline).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    fireEvent.click(screen.getAllByTitle('Delete chapter')[0]);
    await expectAction({
      action: 'delete_chapter', chapter_id: 'chapter-1', delete_lessons: true,
    });

    fireEvent.click(screen.getAllByTitle('Delete lesson')[0]);
    await expectAction({ action: 'delete_lesson', lesson_id: 'lesson-1' });
  });
});
