import '@testing-library/jest-dom';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { OutputPane } from '../../src/components/study/OutputPane';

// scrollIntoView is not implemented in jsdom
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

// Mock the chat service so no real HTTP calls are made
jest.mock('../../src/lib/services/chat', () => ({
  sendChatMessage: jest.fn(),
}));

import { sendChatMessage } from '../../src/lib/services/chat';
const mockSend = sendChatMessage as jest.MockedFunction<typeof sendChatMessage>;

describe('OutputPane', () => {
  const defaultProps = { courseId: 'course-123', accessToken: 'tok' };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  describe('initial render', () => {
    it('renders the AI Tutor heading', () => {
      render(<OutputPane {...defaultProps} />);
      expect(screen.getByText('AI Tutor')).toBeInTheDocument();
    });

    it('renders the message input area', () => {
      render(<OutputPane {...defaultProps} />);
      expect(screen.getByRole('textbox', { name: /message input/i })).toBeInTheDocument();
    });

    it('renders the send button', () => {
      render(<OutputPane {...defaultProps} />);
      expect(screen.getByRole('button', { name: /send message/i })).toBeInTheDocument();
    });

    it('disables send button when input is empty', () => {
      render(<OutputPane {...defaultProps} />);
      expect(screen.getByRole('button', { name: /send message/i })).toBeDisabled();
    });

    it('shows the empty-state prompt when no messages', () => {
      render(<OutputPane {...defaultProps} />);
      expect(screen.getByText(/ask me anything/i)).toBeInTheDocument();
    });

    it('shows lesson-specific placeholder when a lesson is selected', () => {
      render(
        <OutputPane
          {...defaultProps}
          selectedLesson={{ id: 1, title: 'How Mining Works' }}
        />
      );
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      expect(textarea).toHaveAttribute('placeholder', 'Ask about "How Mining Works"…');
    });
  });

  describe('sending a message', () => {
    it('enables send button when input has text', async () => {
      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'What is a UTXO?');
      expect(screen.getByRole('button', { name: /send message/i })).not.toBeDisabled();
    });

    it('shows user message in the thread after send', async () => {
      mockSend.mockResolvedValue({ answer: 'A UTXO is an unspent output.', citations: [], retrievalUsed: false });

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'What is a UTXO?');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      expect(screen.getByText('What is a UTXO?')).toBeInTheDocument();
    });

    it('clears the input after send', async () => {
      mockSend.mockResolvedValue({ answer: 'Answer.', citations: [], retrievalUsed: false });

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Hello');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      expect(textarea).toHaveValue('');
    });

    it('shows loading dots while waiting for response', async () => {
      mockSend.mockImplementation(() => new Promise(() => {})); // never resolves

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Question?');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      expect(screen.getByLabelText(/loading response/i)).toBeInTheDocument();
    });

    it('shows assistant reply after response arrives', async () => {
      mockSend.mockResolvedValue({
        answer: 'Bitcoin is a peer-to-peer currency.',
        citations: [],
        retrievalUsed: false,
      });

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'What is Bitcoin?');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.getByText('Bitcoin is a peer-to-peer currency.')).toBeInTheDocument();
      });
    });

    it('sends via Enter key (without Shift)', async () => {
      mockSend.mockResolvedValue({ answer: 'Answer.', citations: [], retrievalUsed: false });

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Question?{Enter}');

      expect(mockSend).toHaveBeenCalledWith('course-123', 'Question?', 'tok');
    });

    it('calls sendChatMessage with correct courseId and accessToken', async () => {
      mockSend.mockResolvedValue({ answer: 'Ok.', citations: [], retrievalUsed: false });

      render(<OutputPane courseId="my-course" accessToken="my-token" />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Test question');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      expect(mockSend).toHaveBeenCalledWith('my-course', 'Test question', 'my-token');
    });
  });

  describe('citations', () => {
    it('renders citation snippets when the response includes sources', async () => {
      mockSend.mockResolvedValue({
        answer: 'Answer with sources.',
        citations: [
          { snippet: 'The first source text.', score: 0.95 },
          { snippet: 'The second source text.', score: 0.80 },
        ],
        retrievalUsed: true,
      });

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Question?');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.getByText(/the first source text/i)).toBeInTheDocument();
        expect(screen.getByText(/the second source text/i)).toBeInTheDocument();
      });
    });

    it('shows relevance percentage for each citation', async () => {
      mockSend.mockResolvedValue({
        answer: 'Answer.',
        citations: [{ snippet: 'Snippet.', score: 0.92 }],
        retrievalUsed: true,
      });

      render(<OutputPane {...defaultProps} />);
      await userEvent.type(
        screen.getByRole('textbox', { name: /message input/i }),
        'Question?'
      );
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.getByText('Relevance: 92%')).toBeInTheDocument();
      });
    });

    it('shows "Sources" heading when citations are present', async () => {
      mockSend.mockResolvedValue({
        answer: 'Answer.',
        citations: [{ snippet: 'Source.', score: 0.9 }],
        retrievalUsed: true,
      });

      render(<OutputPane {...defaultProps} />);
      await userEvent.type(
        screen.getByRole('textbox', { name: /message input/i }),
        'Q?'
      );
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.getByText('Sources')).toBeInTheDocument();
      });
    });

    it('does not render Sources section when citations array is empty', async () => {
      mockSend.mockResolvedValue({ answer: 'No sources.', citations: [], retrievalUsed: false });

      render(<OutputPane {...defaultProps} />);
      await userEvent.type(
        screen.getByRole('textbox', { name: /message input/i }),
        'Q?'
      );
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.queryByText('Sources')).not.toBeInTheDocument();
      });
    });
  });

  describe('error handling', () => {
    it('shows an error message in the thread when the API call fails', async () => {
      mockSend.mockRejectedValue(new Error('Network error'));

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Question?');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.getByText(/network error/i)).toBeInTheDocument();
      });
    });
  });
});
