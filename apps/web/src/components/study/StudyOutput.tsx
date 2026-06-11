'use client';

import { useMemo, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { ApiStudyResponse } from '@/lib/api/types';
import { CitationCard } from './CitationCard';

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard not available */
    }
  }
  return (
    <button
      onClick={handleCopy}
      title="Copy to clipboard"
      className="opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity p-1 rounded b-thin font-mono text-[10px] tracking-[0.12em]"
    >
      {copied ? '✓' : (
        <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.666 3.888A2.25 2.25 0 0013.5 2.25h-3c-1.03 0-1.9.693-2.166 1.638m7.332 0c.055.194.084.4.084.612v0a.75.75 0 01-.75.75H9a.75.75 0 01-.75-.75v0c0-.212.03-.418.084-.612m7.332 0c.646.049 1.288.11 1.927.184 1.1.128 1.907 1.077 1.907 2.185V19.5a2.25 2.25 0 01-2.25 2.25H6.75A2.25 2.25 0 014.5 19.5V6.257c0-1.108.806-2.057 1.907-2.185a48.208 48.208 0 011.927-.184" />
        </svg>
      )}
    </button>
  );
}

interface StudyOutputProps {
  result: ApiStudyResponse;
  courseId: string;
}

export function StudyOutput({ result, courseId }: StudyOutputProps) {
  const [showSources, setShowSources] = useState(result.action === 'retrieve');

  const hasOutput = result.answer && result.answer.trim().length > 0;
  const hasCitations = result.citations.length > 0;

  return (
    <div className="space-y-4">
      {!hasOutput && !hasCitations && (
        <p className="font-mono text-[11px] opacity-50 italic">
          No results found in course materials.
        </p>
      )}

      {/* Retrieval unavailable — no citations returned for an action that requires them */}
      {!hasCitations && !result.retrieval_used && result.action !== 'retrieve' && hasOutput && (
        <div
          className="b-thin rounded-md px-4 py-3 text-sm"
          style={{ borderColor: '#a55a00', color: '#a55a00' }}
        >
          Retrieval service temporarily unavailable. Response generated without source context — verify facts independently.
        </div>
      )}

      {!hasOutput && hasCitations && result.action !== 'retrieve' && (
        <div
          className="b-thin rounded-md px-4 py-3 text-sm"
          style={{ borderColor: '#a55a00', color: '#a55a00' }}
        >
          LLM generation unavailable. Showing source passages below.
        </div>
      )}

      {hasOutput && (
        <div className="relative group">
          <div className="absolute top-0 right-0 z-10">
            <CopyButton text={result.answer} />
          </div>
          {result.action === 'quiz' ? (
            <QuizOutput text={result.answer} />
          ) : result.action === 'oral' ? (
            <OralOutput text={result.answer} />
          ) : result.action === 'open_questions' ? (
            <QuestionsOutput text={result.answer} />
          ) : (
            <ReactMarkdown className="md-prose" remarkPlugins={[remarkGfm]}>{result.answer}</ReactMarkdown>
          )}
        </div>
      )}

      {/* Sources toggle (non-retrieve actions) */}
      {hasCitations && result.action !== 'retrieve' && (
        <div>
          <button
            onClick={() => setShowSources((v) => !v)}
            className="flex items-center gap-1.5 font-mono text-[11px] tracking-[0.14em] uppercase opacity-70 hover:opacity-100 transition-opacity"
          >
            <svg
              className={`h-3 w-3 transition-transform ${showSources ? 'rotate-90' : ''}`}
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2.5}
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
            </svg>
            {showSources ? 'Hide' : 'Show'} {result.citations.length} source
            {result.citations.length !== 1 ? 's' : ''}
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
  explanation: string;
}

function parseQuizQuestion(raw: string): ParsedQuestion {
  const lines = raw
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  const qLine = lines.find((l) => /^Q\d*[:.]/i.test(l));
  const question = qLine ? qLine.replace(/^Q\d*[:.]\s*/i, '') : raw.trim();
  const options = lines.filter((l) => /^[A-D][).]\s/.test(l));
  const answerLine = lines.find((l) => /^Answer:/i.test(l));
  const correctLetter = answerLine
    ? answerLine.replace(/^Answer:\s*/i, '').trim().charAt(0).toUpperCase()
    : '';
  // Extract explanation: text after "Answer: B) " and before any [ref_N]
  const explanation = answerLine
    ? answerLine
        .replace(/^Answer:\s*[A-D][).]\s*/i, '')
        .replace(/\[ref_\d+\]/gi, '')
        .trim()
    : '';
  return { question, options, correctLetter, explanation };
}

function QuizQuestion({ raw, index }: { raw: string; index: number }) {
  const [selected, setSelected] = useState('');
  const [revealed, setRevealed] = useState(false);
  const { question, options, correctLetter, explanation } = useMemo(() => parseQuizQuestion(raw), [raw]);

  return (
    <div className="b-thin rounded-lg p-4 bg-white dark:bg-blue-dark/20">
      <p className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-50 mb-2">
        Q{index + 1}
      </p>
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
              <p
                className="font-mono text-[11px]"
                style={{ color: selected === correctLetter ? '#1a7f3a' : '#b3261e' }}
              >
                {selected === correctLetter ? '✓ Correct' : `✗ Correct: ${correctLetter}`}
              </p>
            )}
          </div>

          {/* Rationale shown after reveal */}
          {revealed && explanation && (
            <p className="mt-2 text-[12px] leading-snug opacity-70 border-t border-current/10 pt-2">
              {explanation}
            </p>
          )}
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
            <div
              className="mt-2 b-thin rounded-md px-3 py-2"
              style={{ borderColor: '#1a7f3a', background: 'rgba(26,127,58,0.06)' }}
            >
              <p className="font-mono text-[12px]" style={{ color: '#1a7f3a' }}>
                Answer: {correctLetter}
              </p>
              {explanation && (
                <p className="mt-1 text-[12px] leading-snug opacity-70">{explanation}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function QuizOutput({ text }: { text: string }) {
  // Both alternatives accept Q<n>: and Q<n>. to handle LLM format variance.
  const questions = text.split(/\n\s*\n(?=Q\d*[:.])|\n(?=Q\d*[:.] )/g).filter((s) => s.trim());
  if (questions.length === 0) {
    return (
      <pre className="whitespace-pre-wrap font-sans text-[13.5px] leading-relaxed">{text}</pre>
    );
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

interface OralQuestion {
  question: string;
  modelAnswer: string;
  followUp: string;
}

// Labels the ORAL system prompt mandates; plus common LLM deviations.
const _MODEL_ANSWER_RE =
  /(?:Model\s+answer|Model\s+risposta|Answer|Risposta(?:\s+del\s+modello)?):\s*([\s\S]*?)(?:\n(?:Follow-?up|Follow\s+up|Deeper\s+(?:question|probe)|Domanda\s+(?:di\s+)?approfondimento|Approfondimento):|$)/i;
const _FOLLOW_UP_RE =
  /(?:Follow-?up|Follow\s+up|Deeper\s+(?:question|probe)|Domanda\s+(?:di\s+)?approfondimento|Approfondimento):\s*([\s\S]*?)(?:\n(?:Q\d+:|$))/i;

function parseOralOutput(text: string): OralQuestion[] {
  // Accept Q<n>: and Q<n>. as block delimiters.
  const blocks = text.split(/\n\s*\n(?=Q\d+[:.])|\n(?=Q\d+[:.])/g).filter((b) => b.trim());
  if (blocks.length === 0) return [];

  return blocks.map((block) => {
    const lines = block.split('\n');
    // Question: first line matching Q<n>: or Q<n>.
    const qLine = lines.find((l) => /^Q\d+[:.]/i.test(l.trim())) ?? '';
    const question = qLine.replace(/^Q\d+[:.]\s*/i, '').trim();

    // Model answer: text between the answer label and the follow-up label (or end)
    const modelAnswerMatch = block.match(_MODEL_ANSWER_RE);
    const modelAnswer = modelAnswerMatch ? modelAnswerMatch[1].trim() : '';

    // Follow-up: text after the follow-up label
    const followUpMatch = block.match(_FOLLOW_UP_RE);
    const followUp = followUpMatch ? followUpMatch[1].trim() : '';

    return { question, modelAnswer, followUp };
  });
}

type OralPhase = 'idle' | 'submitted' | 'revealed';

function OralQuestionCard({ q, index }: { q: OralQuestion; index: number }) {
  const [phase, setPhase] = useState<OralPhase>('idle');
  const [studentAnswer, setStudentAnswer] = useState('');

  return (
    <div className="b-thin rounded-lg p-4 bg-white dark:bg-blue-dark/20 space-y-3">
      <p className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-50">Q{index + 1}</p>
      <p className="text-[13.5px] font-medium leading-snug">{q.question}</p>

      {phase === 'idle' && (
        <div className="space-y-2">
          <textarea
            value={studentAnswer}
            onChange={(e) => setStudentAnswer(e.target.value)}
            placeholder="Type your answer here…"
            rows={3}
            className="w-full resize-none rounded-md b-thin px-3 py-2 text-sm bg-transparent outline-none focus:ring-1 focus:ring-blue-dark"
          />
          {studentAnswer.trim() && (
            <button
              onClick={() => setPhase('submitted')}
              className="btn-ghost text-[11px]"
            >
              Submit answer →
            </button>
          )}
        </div>
      )}

      {phase !== 'idle' && (
        <div className="b-thin rounded-md px-3 py-2 bg-blue-dark/5 dark:bg-white/5">
          <p className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-50 mb-1">Your answer</p>
          <p className="text-[13px] leading-snug">{studentAnswer}</p>
        </div>
      )}

      {phase === 'submitted' && (
        <button
          onClick={() => setPhase('revealed')}
          className="btn-ghost text-[11px]"
        >
          See model answer ▾
        </button>
      )}

      {phase === 'revealed' && q.modelAnswer && (
        <div className="space-y-2">
          <div
            className="b-thin rounded-md px-3 py-2"
            style={{ borderColor: '#1a7f3a', background: 'rgba(26,127,58,0.05)' }}
          >
            <p className="font-mono text-[10px] tracking-[0.18em] uppercase mb-1" style={{ color: '#1a7f3a' }}>
              Model answer
            </p>
            <p className="text-[13px] leading-snug">{q.modelAnswer}</p>
          </div>
          {q.followUp && (
            <div className="b-thin rounded-md px-3 py-2 bg-blue-dark/5 dark:bg-white/5">
              <p className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-50 mb-1">Follow-up</p>
              <p className="text-[13px] leading-snug italic">{q.followUp}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function OralOutput({ text }: { text: string }) {
  const questions = useMemo(() => parseOralOutput(text), [text]);

  if (questions.length === 0) {
    return (
      <ReactMarkdown className="md-prose" remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    );
  }

  return (
    <div className="space-y-4">
      {questions.map((q, i) => (
        <OralQuestionCard key={i} q={q} index={i} />
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
        <p key={i} className="text-[13.5px] leading-relaxed">
          {line}
        </p>
      ))}
    </div>
  );
}
