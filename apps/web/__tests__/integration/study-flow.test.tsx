import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useSession } from 'next-auth/react';
import { useParams } from 'next/navigation';

// scrollIntoView not implemented in jsdom
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

// ── Module mocks ────────────────────────────────────────────────────────────

jest.mock('next-auth/react', () => ({
  useSession: jest.fn(),
}));

jest.mock('next/navigation', () => ({
  useParams: jest.fn(),
  useRouter: jest.fn(() => ({ push: jest.fn() })),
}));

jest.mock('@/lib/services/courses', () => ({
  getCourse: jest.fn(),
  getCourseLessons: jest.fn(),
}));

jest.mock('@/lib/services/progress', () => ({
  getCourseProgress: jest.fn(),
  markLessonComplete: jest.fn(),
}));

jest.mock('@/lib/services/documents', () => ({
  getDocuments: jest.fn(),
}));

jest.mock('@/lib/api/documents', () => ({
  getDocumentPreviewView: jest.fn(),
}));

jest.mock('@/lib/services/chat', () => ({
  sendChatMessage: jest.fn(),
}));

// ── Imports after mocks ─────────────────────────────────────────────────────

import { getCourse, getCourseLessons } from '@/lib/services/courses';
import { getCourseProgress, markLessonComplete } from '@/lib/services/progress';
import { getDocuments } from '@/lib/services/documents';
import { getDocumentPreviewView } from '@/lib/api/documents';
import { sendChatMessage } from '@/lib/services/chat';

// eslint-disable-next-line @typescript-eslint/no-var-requires
const StudyPage = require('../../src/app/courses/[courseId]/study/page').default;

// ── Shared fixtures ─────────────────────────────────────────────────────────

const COURSE = { id: 'course-123', title: 'Bitcoin Fundamentals', description: 'Learn Bitcoin.' };
const LESSONS = [
  { id: 1, title: 'Introduction to Bitcoin', content: '' },
  { id: 2, title: 'How Mining Works', content: 'Mining is the process...' },
];
const PROGRESS = {
  courseId: 'course-123',
  percent: 0,
  status: 'not_started',
  lessonCount: 2,
  completedCount: 0,
  updatedAt: '2026-01-01T00:00:00Z',
};

function setupMocks() {
  (useSession as jest.Mock).mockReturnValue({
    data: { user: { accessToken: 'test-token' } },
    status: 'authenticated',
  });
  (useParams as jest.Mock).mockReturnValue({ courseId: 'course-123' });
  (getCourse as jest.Mock).mockResolvedValue(COURSE);
  (getCourseLessons as jest.Mock).mockResolvedValue(LESSONS);
  (getCourseProgress as jest.Mock).mockResolvedValue(PROGRESS);
  (getDocuments as jest.Mock).mockResolvedValue([]);
  (getDocumentPreviewView as jest.Mock).mockResolvedValue({
    id: 'doc-1',
    filename: 'guide.pdf',
    extractedTextPreview: null,
    pageCount: null,
    sections: [],
    sampleChunks: [],
  });
}

describe('Study Flow Integration', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    setupMocks();
  });

  describe('initial load', () => {
    it('shows course title after data loads', async () => {
      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByText('Bitcoin Fundamentals')).toBeInTheDocument();
      });
    });

    it('renders all lesson titles in the sidebar', async () => {
      render(<StudyPage />);

      // First lesson title appears in both the nav and the content header (auto-selected)
      await waitFor(() => {
        expect(screen.getAllByText('Introduction to Bitcoin').length).toBeGreaterThanOrEqual(1);
        expect(screen.getByText('How Mining Works')).toBeInTheDocument();
      });
    });

    it('selects the first lesson by default', async () => {
      render(<StudyPage />);

      await waitFor(() => {
        const buttons = screen.getAllByRole('button').filter((b) =>
          b.textContent?.includes('Introduction to Bitcoin')
        );
        expect(buttons[0]).toHaveAttribute('aria-current', 'true');
      });
    });

    it('shows a loading spinner during fetch', () => {
      // Make getCourse never resolve
      (getCourse as jest.Mock).mockImplementation(() => new Promise(() => {}));
      render(<StudyPage />);
      // A loading spinner should be visible
      expect(document.querySelector('.animate-spin')).toBeInTheDocument();
    });

    it('shows course progress bar when progress is loaded', async () => {
      (getCourseProgress as jest.Mock).mockResolvedValue({
        ...PROGRESS,
        percent: 50,
        completedCount: 1,
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByRole('progressbar')).toBeInTheDocument();
      });
    });
  });

  describe('lesson selection', () => {
    it('updates the selected lesson when clicking a different lesson', async () => {
      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByText('How Mining Works')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('How Mining Works'));

      await waitFor(() => {
        const buttons = screen.getAllByRole('button').filter((b) =>
          b.textContent?.includes('How Mining Works')
        );
        expect(buttons[0]).toHaveAttribute('aria-current', 'true');
      });
    });

    it('shows lesson content when a lesson with content is selected', async () => {
      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByText('How Mining Works')).toBeInTheDocument();
      });

      fireEvent.click(screen.getByText('How Mining Works'));

      await waitFor(() => {
        expect(screen.getByText('Mining is the process...')).toBeInTheDocument();
      });
    });
  });

  describe('content chunks display', () => {
    it('shows document chunks when course has ready documents', async () => {
      (getDocuments as jest.Mock).mockResolvedValue([
        { id: 'doc-1', filename: 'bitcoin-guide.pdf', status: 'ready', size: 1024, created_at: '' },
      ]);
      (getDocumentPreviewView as jest.Mock).mockResolvedValue({
        id: 'doc-1',
        filename: 'bitcoin-guide.pdf',
        extractedTextPreview: null,
        pageCount: 5,
        sections: [{ title: 'What is Bitcoin?' }],
        sampleChunks: [
          { text: 'Bitcoin is a decentralized digital currency.', section: 'What is Bitcoin?' },
          { text: 'Transactions are verified by network nodes.', section: 'What is Bitcoin?' },
        ],
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByText('Course Material')).toBeInTheDocument();
        expect(screen.getByText('bitcoin-guide.pdf')).toBeInTheDocument();
        expect(
          screen.getByText('Bitcoin is a decentralized digital currency.')
        ).toBeInTheDocument();
      });
    });

    it('shows section chips for document sections', async () => {
      (getDocuments as jest.Mock).mockResolvedValue([
        { id: 'doc-1', filename: 'guide.pdf', status: 'ready', size: 512, created_at: '' },
      ]);
      (getDocumentPreviewView as jest.Mock).mockResolvedValue({
        id: 'doc-1',
        filename: 'guide.pdf',
        extractedTextPreview: null,
        pageCount: 2,
        sections: [{ title: 'Overview' }, { title: 'Key Concepts' }],
        sampleChunks: [{ text: 'Some chunk text.' }],
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByText('Overview')).toBeInTheDocument();
        expect(screen.getByText('Key Concepts')).toBeInTheDocument();
      });
    });

    it('shows no Course Material section when no ready documents exist', async () => {
      (getDocuments as jest.Mock).mockResolvedValue([
        { id: 'doc-1', filename: 'pending.pdf', status: 'processing', size: 512, created_at: '' },
      ]);

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.queryByText('Course Material')).not.toBeInTheDocument();
      });
    });
  });

  describe('chat integration', () => {
    it('sends a message to the chat service with correct courseId', async () => {
      (sendChatMessage as jest.Mock).mockResolvedValue({
        answer: 'Bitcoin was created in 2009.',
        citations: [],
        retrievalUsed: false,
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByRole('textbox', { name: /message input/i })).toBeInTheDocument();
      });

      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'When was Bitcoin created?');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(sendChatMessage).toHaveBeenCalledWith(
          'course-123',
          'When was Bitcoin created?',
          'test-token'
        );
      });
    });

    it('displays the AI response in the chat thread', async () => {
      (sendChatMessage as jest.Mock).mockResolvedValue({
        answer: 'Satoshi Nakamoto created Bitcoin.',
        citations: [],
        retrievalUsed: false,
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByRole('textbox', { name: /message input/i })).toBeInTheDocument();
      });

      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Who created Bitcoin?');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.getByText('Satoshi Nakamoto created Bitcoin.')).toBeInTheDocument();
      });
    });

    it('shows citations returned with the AI response', async () => {
      (sendChatMessage as jest.Mock).mockResolvedValue({
        answer: 'Bitcoin uses proof of work.',
        citations: [{ snippet: 'Proof of work is the consensus mechanism.', score: 0.88 }],
        retrievalUsed: true,
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByRole('textbox', { name: /message input/i })).toBeInTheDocument();
      });

      await userEvent.type(
        screen.getByRole('textbox', { name: /message input/i }),
        'How does consensus work?'
      );
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.getByText(/proof of work is the consensus mechanism/i)).toBeInTheDocument();
        expect(screen.getByText('Relevance: 88%')).toBeInTheDocument();
      });
    });
  });

  describe('lesson completion', () => {
    it('calls markLessonComplete with correct lessonId and courseId', async () => {
      (markLessonComplete as jest.Mock).mockResolvedValue({
        lessonProgress: { lessonId: '1', status: 'completed', lastScore: null },
        courseProgress: { ...PROGRESS, percent: 50, completedCount: 1 },
        newBadges: [],
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /mark as complete/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /mark as complete/i }));

      await waitFor(() => {
        expect(markLessonComplete).toHaveBeenCalledWith('1', 'course-123', 'test-token');
      });
    });

    it('shows "Lesson completed" after marking complete', async () => {
      (markLessonComplete as jest.Mock).mockResolvedValue({
        lessonProgress: { lessonId: '1', status: 'completed', lastScore: null },
        courseProgress: { ...PROGRESS, percent: 50, completedCount: 1 },
        newBadges: [],
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /mark as complete/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /mark as complete/i }));

      await waitFor(() => {
        expect(screen.getByText('Lesson completed')).toBeInTheDocument();
      });
    });

    it('shows a badge notification when a new badge is earned', async () => {
      (markLessonComplete as jest.Mock).mockResolvedValue({
        lessonProgress: { lessonId: '1', status: 'completed', lastScore: null },
        courseProgress: { ...PROGRESS, percent: 50, completedCount: 1 },
        newBadges: [
          {
            id: 'badge-1',
            slug: 'first-lesson',
            name: 'First Steps',
            description: 'Completed your first lesson',
            icon: '🎯',
          },
        ],
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /mark as complete/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /mark as complete/i }));

      await waitFor(() => {
        expect(screen.getByText(/new badge earned/i)).toBeInTheDocument();
        expect(screen.getByText('First Steps')).toBeInTheDocument();
      });
    });

    it('updates progress bar percentage after marking complete', async () => {
      (markLessonComplete as jest.Mock).mockResolvedValue({
        lessonProgress: { lessonId: '1', status: 'completed', lastScore: null },
        courseProgress: { ...PROGRESS, percent: 50, completedCount: 1 },
        newBadges: [],
      });
      (getCourseProgress as jest.Mock).mockResolvedValue({
        ...PROGRESS,
        percent: 0,
        completedCount: 0,
      });

      render(<StudyPage />);

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /mark as complete/i })).toBeInTheDocument();
      });

      fireEvent.click(screen.getByRole('button', { name: /mark as complete/i }));

      await waitFor(() => {
        expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '50');
      });
    });
  });
});
