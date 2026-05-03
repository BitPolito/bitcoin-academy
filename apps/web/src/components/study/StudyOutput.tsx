'use client';

import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import type { ApiStudyResponse } from '@/lib/api/types';
import { CitationCard } from './CitationCard';

interface StudyOutputProps {
  result: ApiStudyResponse;
  courseId: string;
  onOralFollowUp?: (query: string) => void;
}

export function StudyOutput({ result, courseId, onOralFollowUp }: StudyOutputProps) {
  const [showSources, setShowSources] = useState(result.action === 'retrieve');

  const hasOutput = result.answer && result.answer.trim().length > 0;
  const hasCitations = result.citations.length > 0;

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
        <QuizOutput text={result.answer} />
      ) : hasOutput && result.action === 'oral' ? (
        <OralOutput text={result.answer} onSubmit={onOralFollowUp} />
      ) : hasOutput && result.action === 'open_questions' ? (
        <QuestionsOutput text={result.answer} />
      ) : hasOutput ? (
        <ReactMarkdown className="md-prose">{result.answer}</ReactMarkdown>
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

// ── Quiz ──────────────────────────────────────────────────────────────────────

interface ParsedQuestion {
  question: string;
  options: string[];
  correctLetter: string;
}

function parseQuizQuestion(raw: string): ParsedQuestion {
  const lines = raw.split('\n').map((l) => l.trim()).filter(Boolean);
  const qLine = lines.find((l) => /^Q\d*[:.]/i.test(l));
  const question = qLine ? qLine.replace(/^Q\d*[:.]\s*/i, '') : raw.trim();
  const options = lines.filter((l) => /^[A-D][).]\s/.test(l));
  const answerLine = lines.find((l) => /^Answer:/i.test(l));
  const correctLetter = answerLine
    ? answerLine.replace(/^Answer:\s*/i, '').trim().charAt(0).toUpperCase()
    : '';
  return { question, options, correctLetter };
}

function QuizQuestion({ raw, index }: { raw: string; index: number }) {
  const [selected, setSelected] = useState('');
  const [revealed, setRevealed] = useState(false);
  const { question, options, correctLetter } = useMemo(() => parseQuizQuestion(raw), [raw]);

  return (
    <div className="b-thin rounded-lg p-4 bg-white dark:bg-blue-dark/20">
      <p className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-50 mb-2">Q{index + 1}</p>
      <p className="text-[13.5px] font-medium leading-snug mb-3">{question}</p>

      {options.length > 0 ? (
        <div className="space-y-2">
          {options.map((opt) => {
            const letter = opt.charAt(0).toUpperCase();
            const isCorrect = letter === correctLetter;
            const isSelected = selected === letter;
            return (
              <button
                key={letter}
                onClick={() => !revealed && setSelected(letter)}
                disabled={revealed}
                className={`w-full b-thin rounded-md px-3 py-2 text-left text-[13px] transition-colors ${
                  revealed && isCorrect
                    ? 'bg-[rgba(26,127,58,0.08)] dark:bg-[rgba(26,127,58,0.15)]'
                    : revealed && isSelected && !isCorrect
                    ? 'bg-[rgba(179,38,30,0.08)] dark:bg-[rgba(179,38,30,0.15)]'
                    : isSelected
                    ? 'bg-blue-dark text-white'
                    : 'hover:bg-blue-dark/5 dark:hover:bg-white/5'
                }`}
                style={
                  revealed && isCorrect
                    ? { borderColor: '#1a7f3a' }
                    : revealed && isSelected && !isCorrect
                    ? { borderColor: '#b3261e' }
                    : {}
                }
              >
                {opt}
              </button>
            );
          })}

          <div className="flex items-center gap-3 pt-1">
            {!revealed && selected && (
              <button onClick={() => setRevealed(true)} className="btn-ghost text-[11px]">
                Check answer
              </button>
            )}
            {revealed && (
              <p className="font-mono text-[11px]" style={{ color: selected === correctLetter ? '#1a7f3a' : '#b3261e' }}>
                {selected === correctLetter ? '✓ Correct' : `✗ Correct: ${correctLetter}`}
              </p>
            )}
          </div>
        </div>
      ) : (
        /* Fallback: options not parseable — show plain reveal */
        <div>
          <button
            onClick={() => setRevealed((v) => !v)}
            className="font-mono text-[11px] tracking-[0.14em] uppercase opacity-70 hover:opacity-100"
          >
            {revealed ? 'Hide answer' : 'Reveal answer'}
          </button>
          {revealed && correctLetter && (
            <div className="mt-2 b-thin rounded-md px-3 py-2" style={{ borderColor: '#1a7f3a', background: 'rgba(26,127,58,0.06)' }}>
              <p className="font-mono text-[12px]" style={{ color: '#1a7f3a' }}>Answer: {correctLetter}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function QuizOutput({ text }: { text: string }) {
  const questions = text.split(/\n(?=Q:)/g).filter((s) => s.trim());
  if (questions.length === 0) {
    return <pre className="whitespace-pre-wrap font-sans text-[13.5px] leading-relaxed">{text}</pre>;
  }
  return (
    <div className="space-y-4">
      {questions.map((q, i) => (
        <QuizQuestion key={i} raw={q} index={i} />
      ))}
    </div>
  );
}

// ── Oral ──────────────────────────────────────────────────────────────────────

function OralOutput({ text, onSubmit }: { text: string; onSubmit?: (query: string) => void }) {
  const [answers, setAnswers] = useState<Record<number, string>>({});
  const questions = text.split(/\n(?=Q\d+:)/g).filter((s) => s.trim());

  function handleSubmit(idx: number, questionText: string) {
    const answer = (answers[idx] ?? '').trim();
    if (!answer || !onSubmit) return;
    onSubmit(`${questionText.trim()}\n\nMy answer: ${answer}`);
  }

  function answerBox(idx: number, questionText: string) {
    return (
      <div className="mt-3 space-y-2">
        <textarea
          value={answers[idx] ?? ''}
          onChange={(e) => setAnswers((prev) => ({ ...prev, [idx]: e.target.value }))}
          placeholder="Type your answer here…"
          rows={3}
          className="w-full resize-none rounded-md b-thin px-3 py-2 text-sm bg-transparent outline-none focus:ring-1 focus:ring-blue-dark"
        />
        {(answers[idx] ?? '').trim() && onSubmit && (
          <button onClick={() => handleSubmit(idx, questionText)} className="btn-ghost text-[11px]">
            Submit answer →
          </button>
        )}
      </div>
    );
  }

  if (questions.length === 0) {
    return (
      <div>
        <ReactMarkdown className="md-prose">{text}</ReactMarkdown>
        {answerBox(0, text)}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {questions.map((q, i) => (
        <div key={i} className="b-thin rounded-lg p-4 bg-white dark:bg-blue-dark/20">
          <ReactMarkdown className="md-prose">{q.trim()}</ReactMarkdown>
          {answerBox(i, q)}
        </div>
      ))}
    </div>
  );
}

// ── Open questions ────────────────────────────────────────────────────────────

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
