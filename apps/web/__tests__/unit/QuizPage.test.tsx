import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { useSession } from 'next-auth/react';
import { QuizPage } from '@/components/assessment/QuizPage';
import { SourcePane } from '@/components/study/SourcePane';
import { submitQuizAttempt } from '@/lib/services/chapterTests';

jest.mock('next-auth/react', () => ({ useSession: jest.fn() }));
jest.mock('next/navigation', () => ({ useRouter: () => ({ push: jest.fn() }) }));
jest.mock('@/components/ui/Toast', () => ({ useToast: () => ({ showToast: jest.fn() }) }));
jest.mock('@/components/study/ContentChunks', () => ({ ContentChunks: () => null }));
jest.mock('@/lib/services/chapterTests', () => ({ submitQuizAttempt: jest.fn() }));
const quiz = {
  id: 'lesson-quiz',
  title: 'Saved lesson quiz',
  passing_score: 70,
  questions: [
    {
      id: 'q1',
      prompt: 'Select the supported answer',
      order_index: 0,
      options: [
        { id: 'a', label: 'Answer A' },
        { id: 'b', label: 'Answer B' },
      ],
    },
  ],
};
beforeEach(() => {
  jest.clearAllMocks();
  (useSession as jest.Mock).mockReturnValue({ data: { user: { accessToken: 'learner-token' } } });
});

it('links the selected lesson to its saved quiz', () => {
  render(
    <SourcePane
      courseId="course-1"
      lessons={[]}
      selectedLesson={{ id: 7, title: 'Lesson' }}
      completedLessons={new Set()}
      onSelectLesson={jest.fn()}
      onMarkComplete={jest.fn()}
    />
  );
  expect(screen.getByRole('link', { name: /take lesson quiz/i })).toHaveAttribute(
    'href',
    '/courses/course-1/lessons/7/quiz'
  );
});

it.each([
  [67, false],
  [100, true],
])('shows the server score and passing result (%s)', async (score, passed) => {
  const loadQuiz = jest.fn().mockResolvedValue(quiz);
  (submitQuizAttempt as jest.Mock).mockResolvedValue({
    score_pct: score,
    passed,
    correct_count: passed ? 1 : 0,
    total_count: 1,
    corrections: [],
  });
  render(<QuizPage courseId="course-1" kind="Lesson Quiz" loadQuiz={loadQuiz} />);
  expect(await screen.findByRole('button', { name: /submit answers/i })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'Answer A' }));
  fireEvent.click(screen.getByRole('button', { name: /submit answers/i }));
  await waitFor(() =>
    expect(submitQuizAttempt).toHaveBeenCalledWith('lesson-quiz', { q1: 'a' }, 'learner-token')
  );
  expect(await screen.findByRole('status')).toHaveTextContent(
    `${passed ? 'Passed' : 'Not passed'} — ${score}%`
  );
});

it('waits for authentication and shows a clear state when no quiz exists', async () => {
  const loadQuiz = jest.fn().mockRejectedValue(new Error('No quiz'));
  (useSession as jest.Mock).mockReturnValue({ data: null });
  const { rerender } = render(
    <QuizPage courseId="course-1" kind="Lesson Quiz" loadQuiz={loadQuiz} />
  );
  expect(loadQuiz).not.toHaveBeenCalled();
  (useSession as jest.Mock).mockReturnValue({ data: { user: { accessToken: 'learner-token' } } });
  rerender(<QuizPage courseId="course-1" kind="Lesson Quiz" loadQuiz={loadQuiz} />);
  expect(await screen.findByText('No lesson quiz available yet.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /submit answers/i })).not.toBeInTheDocument();
});
