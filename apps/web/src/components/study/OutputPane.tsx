'use client';

import {
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from 'react';
import { sendChatMessage, type Citation } from '@/lib/services/chat';
import type { Lesson } from '@/lib/services/courses';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
}

interface OutputPaneProps {
  courseId: string;
  accessToken?: string;
  selectedLesson?: Lesson | null;
}

export function OutputPane({ courseId, accessToken, selectedLesson }: OutputPaneProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  async function handleSend() {
    const question = input.trim();
    if (!question || loading) return;

    setInput('');
    setMessages((prev) => [...prev, { role: 'user', content: question }]);
    setLoading(true);

    try {
      const result = await sendChatMessage(courseId, question, accessToken);
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: result.answer,
          citations: result.citations,
        },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content:
            err instanceof Error
              ? `Error: ${err.message}`
              : 'Could not fetch a response. Please try again.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const placeholder = selectedLesson
    ? `Ask about "${selectedLesson.title}"…`
    : 'Ask a question about the course material…';

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
          AI Tutor
        </h2>
        <p className="mt-0.5 text-xs text-gray-500">
          Ask questions about the course material
        </p>
      </div>

      {/* Message thread */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-xs">
              <svg
                className="mx-auto h-12 w-12 text-gray-300"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.455 2.456L21.75 6l-1.036.259a3.375 3.375 0 00-2.455 2.456zM16.894 20.567L16.5 21.75l-.394-1.183a2.25 2.25 0 00-1.423-1.423L13.5 18.75l1.183-.394a2.25 2.25 0 001.423-1.423l.394-1.183.394 1.183a2.25 2.25 0 001.423 1.423l1.183.394-1.183.394a2.25 2.25 0 00-1.423 1.423z"
                />
              </svg>
              <p className="mt-3 text-sm text-gray-500">
                Ask me anything about the course content. I will find relevant passages and explain them.
              </p>
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-orange-600 text-white'
                  : 'bg-gray-100 text-gray-900'
              }`}
            >
              <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>

              {msg.role === 'assistant' &&
                msg.citations &&
                msg.citations.length > 0 && (
                  <div className="mt-3 space-y-2 border-t border-gray-200 pt-2">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">
                      Sources
                    </p>
                    {msg.citations.map((citation, ci) => (
                      <div
                        key={ci}
                        className="rounded-md bg-white border border-gray-200 px-3 py-2"
                      >
                        <p className="text-xs text-gray-700 line-clamp-3 leading-relaxed">
                          &ldquo;{citation.snippet}&rdquo;
                        </p>
                        <p className="mt-1 text-xs text-gray-400">
                          Relevance: {Math.round(citation.score * 100)}%
                        </p>
                      </div>
                    ))}
                  </div>
                )}
            </div>
          </div>
        ))}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-xl px-4 py-3" aria-label="Loading response">
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="h-2 w-2 rounded-full bg-gray-400 animate-bounce"
                    style={{ animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 border-t border-gray-200 p-4">
        <div className="flex gap-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={2}
            disabled={loading}
            aria-label="Message input"
            className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            aria-label="Send message"
            className="flex-shrink-0 inline-flex items-center justify-center h-10 w-10 self-end rounded-lg bg-orange-600 text-white hover:bg-orange-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2"
          >
            <svg
              className="h-5 w-5"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5"
              />
            </svg>
          </button>
        </div>
        <p className="mt-1.5 text-xs text-gray-400">
          Enter to send · Shift+Enter for a new line
        </p>
      </div>
    </div>
  );
}
