'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { useToast } from '@/components/ui/Toast';
import {
  submitQuizAttempt,
  type ChapterTestQuestion,
  type QuizAttemptResult,
} from '@/lib/services/chapterTests';

interface QuizData {
  id: string;
  quiz_id?: string;
  title?: string;
  passing_score: number;
  questions: ChapterTestQuestion[];
}

interface QuizPageProps {
  courseId: string;
  kind: 'Lesson Quiz' | 'Chapter Test';
  loadQuiz: (accessToken: string) => Promise<QuizData>;
}

export function QuizPage({ courseId, kind, loadQuiz }: QuizPageProps) {
  const router = useRouter();
  const { data: session } = useSession();
  const accessToken = session?.user?.accessToken;
  const { showToast } = useToast();

  const [test, setTest] = useState<QuizData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<QuizAttemptResult | null>(null);

  useEffect(() => {
    let active = true;
    async function load(token: string) {
      setLoading(true);
      setResult(null);
      setAnswers({});
      try {
        const data = await loadQuiz(token);
        if (active) {
          setTest(data);
          setError(null);
        }
      } catch {
        if (active) setError(`No ${kind.toLowerCase()} available yet.`);
      } finally {
        if (active) setLoading(false);
      }
    }
    if (accessToken) load(accessToken);
    return () => {
      active = false;
    };
  }, [loadQuiz, kind, accessToken]);

  async function handleSubmit() {
    if (!test) return;
    setSubmitting(true);
    try {
      const res = await submitQuizAttempt(test.quiz_id ?? test.id, answers, accessToken);
      setResult(res);
      showToast(res.passed ? 'Test passed!' : 'Test completed.', res.passed ? 'ok' : 'warn');
    } catch {
      showToast('Could not submit the test. Try again.', 'err');
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <main className="page-fade max-w-3xl mx-auto px-6 py-6">
        <div className="animate-pulse h-64 b-hard rounded-lg bg-blue-dark/5" />
      </main>
    );
  }

  if (error || !test) {
    return (
      <main className="max-w-3xl mx-auto px-6 py-6">
        <div
          className="b-hard rounded-lg p-6 text-center"
          style={{ borderColor: '#b3261e', color: '#b3261e' }}
        >
          <p className="text-sm">{error || 'Test not found'}</p>
          <button
            onClick={() => router.push(`/courses/${courseId}/study`)}
            className="mt-3 text-sm font-medium underline"
          >
            Back to study
          </button>
        </div>
      </main>
    );
  }

  const allAnswered = test.questions.every((q) => answers[q.id]);

  return (
    <main className="page-fade max-w-3xl mx-auto px-6 py-6">
      <ErrorBoundary>
        <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 px-6 py-5 mb-5">
          <div className="flex items-center gap-2 font-mono text-[11px] tracking-[0.12em] uppercase opacity-70 mb-2">
            <span>{kind}</span>
          </div>
          <h1 className="text-2xl font-medium leading-tight">{test.title || kind}</h1>
          <p className="font-mono text-[11px] opacity-60 mt-1">
            {test.questions.length} questions · passing score {test.passing_score}%
          </p>
        </div>

        {result && (
          <div
            className="b-hard rounded-lg px-6 py-5 mb-5"
            role="status"
            style={{ borderColor: result.passed ? '#1a7f3a' : '#a55a00' }}
          >
            <p
              className="text-lg font-medium"
              style={{ color: result.passed ? '#1a7f3a' : '#a55a00' }}
            >
              {result.passed ? '✓ Passed' : 'Not passed'} — {result.score_pct}%
            </p>
            <p className="font-mono text-[11px] opacity-70 mt-1">
              {result.correct_count} / {result.total_count} correct
            </p>
          </div>
        )}

        <div className="space-y-4">
          {test.questions.map((q, i) => {
            const correction = result?.corrections.find((c) => c.question_id === q.id);
            return (
              <div key={q.id} className="b-hard rounded-lg p-4 bg-white dark:bg-blue-dark/20">
                <p className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-50 mb-2">
                  Q{i + 1}
                </p>
                <p className="text-[13.5px] font-medium leading-snug mb-3">{q.prompt}</p>
                <div className="space-y-2">
                  {q.options.map((opt) => {
                    const isSelected = answers[q.id] === opt.id;
                    const isCorrectAnswer = correction?.correct_option_id === opt.id;
                    const isWrongSelected = !!result && isSelected && !correction?.is_correct;
                    return (
                      <button
                        key={opt.id}
                        onClick={() => !result && setAnswers((a) => ({ ...a, [q.id]: opt.id }))}
                        disabled={!!result}
                        className={`w-full b-thin rounded-md px-3 py-2 text-left text-[13px] transition-colors ${
                          result && isCorrectAnswer
                            ? 'bg-[rgba(26,127,58,0.08)] dark:bg-[rgba(26,127,58,0.15)]'
                            : isWrongSelected
                              ? 'bg-[rgba(179,38,30,0.08)] dark:bg-[rgba(179,38,30,0.15)]'
                              : isSelected
                                ? 'bg-blue-dark text-white'
                                : 'hover:bg-blue-dark/5 dark:hover:bg-white/5'
                        }`}
                        style={
                          result && isCorrectAnswer
                            ? { borderColor: '#1a7f3a' }
                            : isWrongSelected
                              ? { borderColor: '#b3261e' }
                              : {}
                        }
                      >
                        {opt.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        <div className="mt-5 flex items-center gap-3">
          {!result ? (
            <button
              className="btn-primary"
              onClick={handleSubmit}
              disabled={!allAnswered || submitting}
            >
              {submitting ? 'Submitting…' : 'Submit answers'}
            </button>
          ) : (
            <button className="btn-ghost" onClick={() => router.push(`/courses/${courseId}/study`)}>
              ← Back to study
            </button>
          )}
        </div>
      </ErrorBoundary>
    </main>
  );
}
