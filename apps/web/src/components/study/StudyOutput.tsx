'use client';

import { useState } from 'react';
import type { ApiStudyResponse } from '@/lib/api/types';
import { CitationCard } from './CitationCard';

interface StudyOutputProps {
  result: ApiStudyResponse;
  courseId: string;
}

export function StudyOutput({ result, courseId }: StudyOutputProps) {
  const [showSources, setShowSources] = useState(result.action === 'retrieve');
  const [revealedAnswers, setRevealedAnswers] = useState<Set<number>>(new Set());

  const hasOutput = result.output && result.output.trim().length > 0;
  const hasChunks = result.evidence.chunks.length > 0;

  function toggleReveal(i: number) {
    setRevealedAnswers((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      {/* Main output */}
      {!hasOutput && !hasChunks && (
        <p className="text-sm text-gray-400 italic">No results found in course materials.</p>
      )}

      {!hasOutput && hasChunks && result.action !== 'retrieve' && (
        <div className="rounded-md bg-yellow-50 border border-yellow-200 px-4 py-3 text-sm text-yellow-800">
          LLM generation unavailable (OPENAI_API_KEY not configured). Showing source passages below.
        </div>
      )}

      {hasOutput && result.action === 'quiz' ? (
        <QuizOutput text={result.output} revealedAnswers={revealedAnswers} onToggle={toggleReveal} />
      ) : hasOutput && result.action === 'oral' ? (
        <OralOutput text={result.output} />
      ) : hasOutput && result.action === 'open_questions' ? (
        <QuestionsOutput text={result.output} />
      ) : hasOutput ? (
        <div className="prose prose-sm max-w-none text-gray-800">
          <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{result.output}</pre>
        </div>
      ) : null}

      {/* Sources section */}
      {hasChunks && result.action !== 'retrieve' && (
        <div>
          <button
            onClick={() => setShowSources((v) => !v)}
            className="flex items-center gap-1 text-xs font-medium text-orange-600 hover:text-orange-700"
          >
            <svg
              className={`h-3.5 w-3.5 transition-transform ${showSources ? 'rotate-90' : ''}`}
              fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            {showSources ? 'Hide' : 'Show'} {result.evidence.chunks.length} source{result.evidence.chunks.length !== 1 ? 's' : ''}
          </button>
          {showSources && (
            <div className="mt-2 space-y-2">
              {result.evidence.chunks.map((chunk, i) => (
                <CitationCard key={chunk.chunk_id} chunk={chunk} courseId={courseId} index={i + 1} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Retrieve: always show chunks directly */}
      {result.action === 'retrieve' && hasChunks && (
        <div className="space-y-2">
          {result.evidence.chunks.map((chunk, i) => (
            <CitationCard key={chunk.chunk_id} chunk={chunk} courseId={courseId} index={i + 1} />
          ))}
        </div>
      )}
    </div>
  );
}

function QuizOutput({
  text,
  revealedAnswers,
  onToggle,
}: {
  text: string;
  revealedAnswers: Set<number>;
  onToggle: (i: number) => void;
}) {
  const questions = text.split(/\n(?=Q:)/g).filter((s) => s.trim());
  if (questions.length === 0) {
    return <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800">{text}</pre>;
  }
  return (
    <div className="space-y-4">
      {questions.map((q, i) => {
        const [questionPart, answerPart] = q.split(/Answer:/i);
        const revealed = revealedAnswers.has(i);
        return (
          <div key={i} className="rounded-lg border border-gray-200 p-4 bg-white">
            <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800">{questionPart.trim()}</pre>
            <button
              onClick={() => onToggle(i)}
              className="mt-3 text-xs font-medium text-orange-600 hover:text-orange-700"
            >
              {revealed ? 'Hide answer' : 'Reveal answer'}
            </button>
            {revealed && answerPart && (
              <div className="mt-2 rounded-md bg-green-50 border border-green-200 px-3 py-2">
                <p className="text-xs font-medium text-green-700">Answer: {answerPart.trim()}</p>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

function OralOutput({ text }: { text: string }) {
  const questions = text.split(/\n(?=Q\d+:)/g).filter((s) => s.trim());
  if (questions.length === 0) {
    return <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800">{text}</pre>;
  }
  return (
    <div className="space-y-4">
      {questions.map((q, i) => (
        <div key={i} className="rounded-lg border border-gray-200 p-4 bg-white">
          <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800">{q.trim()}</pre>
          <textarea
            placeholder="Type your answer here…"
            rows={3}
            className="mt-3 w-full resize-none rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-800 placeholder-gray-400 focus:border-orange-500 focus:outline-none focus:ring-1 focus:ring-orange-500"
          />
        </div>
      ))}
    </div>
  );
}

function QuestionsOutput({ text }: { text: string }) {
  const lines = text.split('\n').filter((l) => l.trim());
  return (
    <div className="space-y-2">
      {lines.map((line, i) => (
        <p key={i} className="text-sm text-gray-800 leading-relaxed">{line}</p>
      ))}
    </div>
  );
}
