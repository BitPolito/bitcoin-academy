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

  const hasOutput = result.answer && result.answer.trim().length > 0;
  const hasCitations = result.citations.length > 0;

  function toggleReveal(i: number) {
    setRevealedAnswers((prev) => {
      const next = new Set(prev);
      next.has(i) ? next.delete(i) : next.add(i);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      {!hasOutput && !hasCitations && (
        <p className="font-mono text-[11px] opacity-50 italic">No results found in course materials.</p>
      )}

      {!hasOutput && hasCitations && result.action !== 'retrieve' && (
        <div className="b-thin rounded-md px-4 py-3 text-sm" style={{ borderColor: '#a55a00', color: '#a55a00' }}>
          LLM generation unavailable (OPENAI_API_KEY not configured). Showing source passages below.
        </div>
      )}

      {hasOutput && result.action === 'quiz' ? (
        <QuizOutput text={result.answer} revealedAnswers={revealedAnswers} onToggle={toggleReveal} />
      ) : hasOutput && result.action === 'oral' ? (
        <OralOutput text={result.answer} />
      ) : hasOutput && result.action === 'open_questions' ? (
        <QuestionsOutput text={result.answer} />
      ) : hasOutput ? (
        <div className="text-[13.5px] leading-relaxed">
          <pre className="whitespace-pre-wrap font-sans">{result.answer}</pre>
        </div>
      ) : null}

      {/* Sources toggle (non-retrieve actions) */}
      {hasCitations && result.action !== 'retrieve' && (
        <div>
          <button
            onClick={() => setShowSources((v) => !v)}
            className="flex items-center gap-1.5 font-mono text-[11px] tracking-[0.14em] uppercase opacity-70 hover:opacity-100 transition-opacity"
          >
            <svg
              className={`h-3 w-3 transition-transform ${showSources ? 'rotate-90' : ''}`}
              fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            {showSources ? 'Hide' : 'Show'} {result.citations.length} source{result.citations.length !== 1 ? 's' : ''}
          </button>
          {showSources && (
            <div className="mt-2 space-y-2">
              {result.citations.map((citation, i) => (
                <CitationCard key={i} citation={citation} courseId={courseId} index={i + 1} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Retrieve: always show citations directly */}
      {result.action === 'retrieve' && hasCitations && (
        <div className="space-y-2">
          {result.citations.map((citation, i) => (
            <CitationCard key={i} citation={citation} courseId={courseId} index={i + 1} />
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
    return <pre className="whitespace-pre-wrap font-sans text-[13.5px] leading-relaxed">{text}</pre>;
  }
  return (
    <div className="space-y-4">
      {questions.map((q, i) => {
        const [questionPart, answerPart] = q.split(/Answer:/i);
        const revealed = revealedAnswers.has(i);
        return (
          <div key={i} className="b-thin rounded-lg p-4 bg-white dark:bg-blue-dark/20">
            <pre className="whitespace-pre-wrap font-sans text-[13.5px] leading-relaxed">{questionPart.trim()}</pre>
            <button
              onClick={() => onToggle(i)}
              className="mt-3 font-mono text-[11px] tracking-[0.14em] uppercase opacity-70 hover:opacity-100"
            >
              {revealed ? 'Hide answer' : 'Reveal answer'}
            </button>
            {revealed && answerPart && (
              <div className="mt-2 b-thin rounded-md px-3 py-2" style={{ borderColor: '#1a7f3a', background: 'rgba(26,127,58,0.06)' }}>
                <p className="font-mono text-[12px]" style={{ color: '#1a7f3a' }}>Answer: {answerPart.trim()}</p>
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
    return <pre className="whitespace-pre-wrap font-sans text-[13.5px] leading-relaxed">{text}</pre>;
  }
  return (
    <div className="space-y-4">
      {questions.map((q, i) => (
        <div key={i} className="b-thin rounded-lg p-4 bg-white dark:bg-blue-dark/20">
          <pre className="whitespace-pre-wrap font-sans text-[13.5px] leading-relaxed">{q.trim()}</pre>
          <textarea
            placeholder="Type your answer here…"
            rows={3}
            className="mt-3 w-full resize-none rounded-md b-thin px-3 py-2 text-sm bg-transparent outline-none focus:ring-1 focus:ring-blue-dark"
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
        <p key={i} className="text-[13.5px] leading-relaxed">{line}</p>
      ))}
    </div>
  );
}
