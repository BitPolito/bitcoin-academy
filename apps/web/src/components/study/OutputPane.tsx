'use client';

import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { sendChatMessage, type Citation } from '@/lib/services/chat';
import { sendStudyAction } from '@/lib/services/study';
import type { ApiStudyResponse, StudyAction } from '@/lib/api/types';
import type { Lesson } from '@/lib/services/courses';
import { StudyActionBar } from './StudyActionBar';
import { StudyOutput } from './StudyOutput';

interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  citations?: Citation[];
}

interface ActionMessage {
  role: 'action-result';
  action: StudyAction;
  query: string;
  result: ApiStudyResponse;
}

type Message = ChatMessage | ActionMessage;

interface OutputPaneProps {
  courseId: string;
  accessToken?: string;
  selectedLesson?: Lesson | null;
}

export function OutputPane({ courseId, accessToken, selectedLesson }: OutputPaneProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [activeAction, setActiveAction] = useState<StudyAction | null>(null);
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
    setActiveAction(null);
    try {
      const result = await sendChatMessage(courseId, question, accessToken);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: result.answer, citations: result.citations },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: err instanceof Error ? `Error: ${err.message}` : 'Could not fetch a response.',
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleAction(action: StudyAction) {
    const query = input.trim() || selectedLesson?.title || 'this course material';
    setLoading(true);
    setActiveAction(action);
    setMessages((prev) => [...prev, { role: 'user', content: `[${action}] ${query}` }]);
    try {
      const result = await sendStudyAction(courseId, action, query, accessToken, selectedLesson?.title);
      setMessages((prev) => [...prev, { role: 'action-result', action, query, result }]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: err instanceof Error ? `Error: ${err.message}` : 'Study action failed.',
        },
      ]);
    } finally {
      setLoading(false);
      setActiveAction(null);
    }
  }

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const placeholder = selectedLesson
    ? `Ask about "${selectedLesson.title}" or pick an action above…`
    : 'Ask a question, or type a topic and pick a study action above…';

  return (
    <div className="h-full flex flex-col bg-white">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-gray-200">
        <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">AI Tutor</h2>
        <p className="mt-0.5 text-xs text-gray-500">Ask questions or run a study action</p>
      </div>

      {/* Action bar */}
      <StudyActionBar
        onAction={handleAction}
        activeAction={activeAction}
        loading={loading}
      />

      {/* Message thread */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-xs">
              <svg className="mx-auto h-12 w-12 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
              </svg>
              <p className="mt-3 text-sm text-gray-500">
                Type a topic in the input below, then click a study action — or just ask a question.
              </p>
            </div>
          </div>
        )}

        {messages.map((msg, i) => {
          if (msg.role === 'action-result') {
            return (
              <div key={i} className="space-y-2">
                <div className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full bg-orange-100 text-orange-700 text-xs font-medium">
                  <span className="capitalize">{msg.action.replace('_', ' ')}</span>
                  <span className="text-orange-400">·</span>
                  <span className="text-orange-600 truncate max-w-48">{msg.query}</span>
                </div>
                <div className="rounded-xl bg-gray-50 border border-gray-200 p-4">
                  <StudyOutput result={msg.result} courseId={courseId} />
                </div>
              </div>
            );
          }

          return (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-xl px-4 py-3 ${msg.role === 'user' ? 'bg-orange-600 text-white' : 'bg-gray-100 text-gray-900'}`}>
                <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 space-y-2 border-t border-gray-200 pt-2">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Sources</p>
                    {msg.citations.map((citation, ci) => (
                      <div key={ci} className="rounded-md bg-white border border-gray-200 px-3 py-2">
                        <p className="text-xs text-gray-700 line-clamp-3 leading-relaxed">&ldquo;{citation.snippet}&rdquo;</p>
                        <p className="mt-1 text-xs text-gray-400">Relevance: {Math.round(citation.score * 100)}%</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex justify-start">
            <div className="bg-gray-100 rounded-xl px-4 py-3">
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <div key={i} className="h-2 w-2 rounded-full bg-gray-400 animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />
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
            className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="flex-shrink-0 inline-flex items-center justify-center h-10 w-10 self-end rounded-lg bg-orange-600 text-white hover:bg-orange-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          </button>
        </div>
        <p className="mt-1.5 text-xs text-gray-400">Enter to send · Shift+Enter for new line · or click an action above</p>
      </div>
    </div>
  );
}
