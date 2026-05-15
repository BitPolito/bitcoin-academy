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
  sendChatMessageStream: jest.fn(),
  submitFeedback: jest.fn(),
}));

import { sendChatMessageStream } from '../../src/lib/services/chat';
const mockSend = sendChatMessageStream as jest.MockedFunction<typeof sendChatMessageStream>;

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
      expect(screen.getByText(/type a topic/i)).toBeInTheDocument();
    });

    it('shows lesson-specific placeholder when a lesson is selected', () => {
      render(
        <OutputPane
          {...defaultProps}
          selectedLesson={{ id: 1, title: 'How Mining Works' }}
        />
      );
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      expect(textarea).toHaveAttribute('placeholder', 'Ask about "How Mining Works" or pick an action above…');
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
      mockSend.mockImplementation(async () => {});

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'What is a UTXO?');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      expect(screen.getByText('What is a UTXO?')).toBeInTheDocument();
    });

    it('clears the input after send', async () => {
      mockSend.mockImplementation(async () => {});

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
      mockSend.mockImplementation(async (_c, _m, onToken) => {
        onToken('Bitcoin is a peer-to-peer currency.');
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
      mockSend.mockImplementation(async () => {});

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Question?{Enter}');

      expect(mockSend).toHaveBeenCalledWith(
        'course-123',
        'Question?',
        expect.any(Function),
        expect.any(Function),
        'tok',
        expect.any(Array),
      );
    });

    it('calls sendChatMessageStream with correct courseId and accessToken', async () => {
      mockSend.mockImplementation(async () => {});

      render(<OutputPane courseId="my-course" accessToken="my-token" />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Test question');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      expect(mockSend).toHaveBeenCalledWith(
        'my-course',
        'Test question',
        expect.any(Function),
        expect.any(Function),
        'my-token',
        expect.any(Array),
      );
    });
  });

  describe('citations', () => {
    it('renders citation snippets when the response includes sources', async () => {
      mockSend.mockImplementation(async (_c, _m, onToken, onCitations) => {
        onToken('Answer with sources.');
        onCitations([
          { snippet: 'The first source text.', score: 0.95 },
          { snippet: 'The second source text.', score: 0.80 },
        ]);
      });

      render(<OutputPane {...defaultProps} />);
      const textarea = screen.getByRole('textbox', { name: /message input/i });
      await userEvent.type(textarea, 'Question?');
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /show 2 sources/i }));
      });
      await waitFor(() => {
        expect(screen.getByText(/the first source text/i)).toBeInTheDocument();
        expect(screen.getByText(/the second source text/i)).toBeInTheDocument();
      });
    });

    it('shows relevance percentage for each citation', async () => {
      mockSend.mockImplementation(async (_c, _m, onToken, onCitations) => {
        onToken('Answer.');
        onCitations([{ snippet: 'Snippet.', score: 0.92 }]);
      });

      render(<OutputPane {...defaultProps} />);
      await userEvent.type(
        screen.getByRole('textbox', { name: /message input/i }),
        'Question?'
      );
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        fireEvent.click(screen.getByRole('button', { name: /show 1 source/i }));
      });
      await waitFor(() => {
        expect(screen.getByText(/92%/)).toBeInTheDocument();
      });
    });

    it('shows source toggle button when citations are present', async () => {
      mockSend.mockImplementation(async (_c, _m, onToken, onCitations) => {
        onToken('Answer.');
        onCitations([{ snippet: 'Source.', score: 0.9 }]);
      });

      render(<OutputPane {...defaultProps} />);
      await userEvent.type(
        screen.getByRole('textbox', { name: /message input/i }),
        'Q?'
      );
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.getByRole('button', { name: /show 1 source/i })).toBeInTheDocument();
      });
    });

    it('does not render Sources section when citations array is empty', async () => {
      mockSend.mockImplementation(async () => {});

      render(<OutputPane {...defaultProps} />);
      await userEvent.type(
        screen.getByRole('textbox', { name: /message input/i }),
        'Q?'
      );
      fireEvent.click(screen.getByRole('button', { name: /send message/i }));

      await waitFor(() => {
        expect(screen.queryByRole('button', { name: /show.*source/i })).not.toBeInTheDocument();
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
