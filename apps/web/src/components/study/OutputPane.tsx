'use client';

import Link from 'next/link';
import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { sendChatMessage, type Citation } from '@/lib/services/chat';
import { sendStudyAction } from '@/lib/services/study';
import type { ApiCitationOut, ApiStudyResponse, StudyAction } from '@/lib/api/types';
import type { Lesson } from '@/lib/services/courses';
import { StudyActionBar } from './StudyActionBar';
import { StudyOutput } from './StudyOutput';

// ── Types ─────────────────────────────────────────────────────────────────────

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
  durationMs?: number;
}

type Message = ChatMessage | ActionMessage;

interface OutputPaneProps {
  courseId: string;
  accessToken?: string;
  selectedLesson?: Lesson | null;
  hasIndexedDocs?: boolean;
  initialQuery?: string;
  initialAction?: StudyAction | null;
  onActionResult?: (result: ApiStudyResponse, lesson: Lesson | null) => void;
}

// ── Evidence Drawer ───────────────────────────────────────────────────────────

function ScoreBar({ score, rerank }: { score: number; rerank?: number }) {
  const r = rerank ?? score;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-3 b-thin relative overflow-hidden">
        <div className="absolute inset-y-0 left-0 h-full opacity-30" style={{ width: `${score * 100}%`, background: '#001CE0' }} />
        <div className="absolute inset-y-0 left-0 h-full" style={{ width: `${r * 100}%`, background: '#001CE0' }} />
      </div>
      <span className="font-mono text-[10px] opacity-70 w-10 text-right tabular-nums">{r.toFixed(3)}</span>
    </div>
  );
}

function EvidenceDrawer({ citations }: { citations: ApiCitationOut[] }) {
  // Group by doc_id for "By source" section
  const byDoc: Record<string, { label: string; count: number }> = {};
  citations.forEach((c) => {
    const key = c.doc_id || 'unknown';
    if (!byDoc[key]) byDoc[key] = { label: c.label || c.doc_id || 'Unknown', count: 0 };
    byDoc[key].count++;
  });
  const total = citations.length || 1;
  const sources = Object.entries(byDoc).map(([, v]) => ({
    label: v.label,
    pct: Math.round((v.count / total) * 100),
  }));

  return (
    <div className="b-thin rounded-lg bg-white dark:bg-blue-dark/20 p-4">
      <div className="grid grid-cols-12 gap-3">
        {/* Passage cards */}
        <div className="col-span-12 lg:col-span-7 space-y-2">
          {citations.map((ev, i) => (
            <div key={i} className="b-thin rounded-md p-3">
              <div className="flex items-center gap-3 mb-1.5">
                <span className="font-mono text-[10px] opacity-70 w-5">[{i + 1}]</span>
                <span className="text-[12.5px] font-medium truncate flex-1">
                  {ev.label || ev.doc_id || 'Source'}
                </span>
                {ev.section && (
                  <span className="chip text-[10px]" style={{ border: '1px solid currentColor' }}>
                    {ev.section}
                  </span>
                )}
              </div>
              <div className="font-mono text-[10px] opacity-60 mb-2">
                {ev.page > 0 && `p.${ev.page}`}
                {ev.slide > 0 && ` · slide ${ev.slide}`}
                {` · score ${ev.score.toFixed(3)}`}
              </div>
              <p className="text-[12.5px] leading-snug opacity-90">{ev.snippet}</p>
              <ScoreBar score={ev.score} />
            </div>
          ))}
        </div>

        {/* Charts */}
        <div className="col-span-12 lg:col-span-5 space-y-3">
          {/* Score bars legend */}
          <div className="b-thin rounded-md p-3">
            <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-2">Score</div>
            <div className="space-y-1.5">
              {citations.map((ev, i) => (
                <div key={i} className="flex items-center gap-2">
                  <span className="font-mono text-[10px] opacity-70 w-5">[{i + 1}]</span>
                  <ScoreBar score={ev.score} />
                </div>
              ))}
            </div>
            <div className="flex items-center gap-3 pt-2 b-thin-t mt-2 font-mono text-[10px] opacity-70">
              <span>
                <span className="inline-block w-2.5 h-2.5 align-middle mr-1" style={{ background: '#001CE0' }} />
                retrieval score
              </span>
            </div>
          </div>

          {/* By source */}
          <div className="b-thin rounded-md p-3">
            <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-2">By source</div>
            <ul className="space-y-1.5">
              {sources.map((s, i) => (
                <li key={i}>
                  <div className="flex items-center justify-between font-mono text-[10px] mb-0.5">
                    <span className="truncate opacity-90">{s.label}</span>
                    <span className="opacity-70 tabular-nums ml-2">{s.pct}%</span>
                  </div>
                  <div className="h-1.5 b-thin overflow-hidden">
                    <div className="h-full" style={{ width: `${s.pct}%`, background: '#001CE0' }} />
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Inspect Drawer ────────────────────────────────────────────────────────────

function InspectDrawer({ msg }: { msg: ActionMessage }) {
  const { action, query, result, durationMs } = msg;
  const lines = {
    'retrieval.trace': [
      `action: ${action}`,
      `query_length: ${query.length} chars`,
      `retrieval_used: ${result.retrieval_used}`,
      `chunks_found: ${result.citations.length}`,
      `generation: ${result.citations.length > 0 ? 'ran' : 'fallback'}`,
      `output_length: ${result.answer.length} chars`,
      durationMs != null ? `duration: ${durationMs}ms` : '(duration not tracked)',
    ],
    'evidence.json': [
      '{',
      `  "action": "${action}",`,
      `  "k": ${result.citations.length},`,
      `  "sources": [${[...new Set(result.citations.map(c => c.doc_id || 'unknown'))].map(d => `"${d}"`).join(', ')}],`,
      `  "avg_score": ${result.citations.length ? (result.citations.reduce((s, c) => s + c.score, 0) / result.citations.length).toFixed(3) : 0}`,
      '}',
    ],
    'output.meta': [
      `model: qvac-rag`,
      `answer_length: ${result.answer.length} chars`,
      `citations: ${result.citations.length}`,
      `retrieval_used: ${result.retrieval_used}`,
    ],
  };

  return (
    <div className="b-thin rounded-lg bg-white dark:bg-blue-dark/20 p-4 mt-2">
      <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-3">
        Inspect · debug · MVP-only
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        {Object.entries(lines).map(([title, content]) => (
          <div key={title} className="b-thin rounded-md overflow-hidden">
            <div className="px-3 py-2 b-thin-b font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">
              {title}
            </div>
            <pre className="font-mono text-[11px] leading-relaxed p-3 whitespace-pre-wrap m-0">
              {content.join('\n')}
            </pre>
          </div>
        ))}
      </div>
    </div>
  );
}

// ── Suggested next actions ────────────────────────────────────────────────────

const NEXT_ACTIONS: Array<{ action: StudyAction; glyph: string; label: string }> = [
  { action: 'derive',  glyph: '∂',  label: 'Derive / prove' },
  { action: 'quiz',    glyph: '▢',  label: 'Quiz me' },
  { action: 'oral',    glyph: '◉',  label: 'Oral follow-ups' },
];

// ── Main component ────────────────────────────────────────────────────────────

export function OutputPane({
  courseId,
  accessToken,
  selectedLesson,
  hasIndexedDocs = true,
  initialQuery = '',
  initialAction = null,
  onActionResult,
}: OutputPaneProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState(initialQuery);
  const [loading, setLoading] = useState(false);
  const [activeAction, setActiveAction] = useState<StudyAction | null>(null);
  const [showEvidence, setShowEvidence] = useState(false);
  const [showInspect, setShowInspect] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const didAutoFireRef = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, loading]);

  // Last action result for drawers
  const lastActionResult = [...messages].reverse().find(
    (m): m is ActionMessage => m.role === 'action-result'
  );

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
        { role: 'assistant', content: err instanceof Error ? `Error: ${err.message}` : 'Could not fetch a response.' },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function handleAction(action: StudyAction, queryOverride?: string) {
    const query = queryOverride || input.trim() || selectedLesson?.title || 'this course material';
    setLoading(true);
    setActiveAction(action);
    setMessages((prev) => [...prev, { role: 'user', content: `[${action}] ${query}` }]);
    const t0 = Date.now();
    try {
      const result = await sendStudyAction(courseId, action, query, accessToken);
      const durationMs = Date.now() - t0;
      setMessages((prev) => [...prev, { role: 'action-result', action, query, result, durationMs }]);
      if (result.citations.length > 0) setShowEvidence(true);
      onActionResult?.(result, selectedLesson ?? null);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: err instanceof Error ? `Error: ${err.message}` : 'Study action failed.' },
      ]);
    } finally {
      setLoading(false);
      setActiveAction(null);
    }
  }

  // Auto-fire when arriving from preview quick actions (?q=...&action=...)
  useEffect(() => {
    if (didAutoFireRef.current || !initialQuery || !initialAction || !hasIndexedDocs || !accessToken) return;
    didAutoFireRef.current = true;
    handleAction(initialAction, initialQuery);
  // handleAction is recreated each render — intentionally not listed to avoid loops.
  // This effect re-evaluates only when auth/docs status changes.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasIndexedDocs, accessToken]);

  function handleKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }

  const placeholder = selectedLesson
    ? `Ask about "${selectedLesson.title}" or pick an action above…`
    : 'Ask a question, or type a topic and pick a study action above…';

  const evidenceCitations = lastActionResult?.result?.citations ?? [];

  return (
    <div className="h-full flex flex-col bg-white dark:bg-blue-dark/30">
      {/* Header */}
      <div className="flex-shrink-0 px-5 py-3 b-thin-b flex items-center gap-3">
        <span className="mono text-[10px] tracking-[0.22em] uppercase opacity-70">AI Tutor</span>
        {selectedLesson && (
          <span className="font-medium text-sm truncate">{selectedLesson.title}</span>
        )}
        {lastActionResult && (
          <div className="ml-auto flex items-center gap-1">
            <button
              onClick={() => { setShowEvidence(v => !v); setShowInspect(false); }}
              className={`font-mono text-[10px] tracking-[0.18em] uppercase px-2.5 h-7 rounded-md transition-all ${
                showEvidence
                  ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                  : 'b-thin hover:bg-blue-dark/5'
              }`}
            >
              {showEvidence ? '▾' : '▸'} Evidence · {evidenceCitations.length}
            </button>
            <button
              onClick={() => { setShowInspect(v => !v); setShowEvidence(false); }}
              className={`font-mono text-[10px] tracking-[0.18em] uppercase px-2.5 h-7 rounded-md transition-all ${
                showInspect
                  ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                  : 'b-thin hover:bg-blue-dark/5'
              }`}
            >
              {showInspect ? '▾' : '▸'} Inspect
            </button>
          </div>
        )}
      </div>

      {/* Action bar */}
      <StudyActionBar
        onAction={handleAction}
        activeAction={activeAction}
        loading={loading}
        hasIndexedDocs={hasIndexedDocs}
      />

      {/* Message thread */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 ws-scroll">
        {/* Empty states */}
        {messages.length === 0 && !hasIndexedDocs && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-xs">
              <div className="mx-auto w-10 h-10 b-thin rounded-md mb-4 stripes" />
              <p className="font-medium mb-1">No documents indexed yet</p>
              <p className="font-mono text-[11px] opacity-60 leading-relaxed mb-4">
                Upload course material in the Workspace to enable study actions.
              </p>
              <Link href={`/courses/${courseId}`} className="btn-ghost text-sm inline-flex">
                Go to Workspace →
              </Link>
            </div>
          </div>
        )}
        {messages.length === 0 && hasIndexedDocs && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center max-w-xs">
              <div className="mx-auto w-10 h-10 b-thin rounded-md mb-4 stripes" />
              <p className="font-mono text-[11px] opacity-60 leading-relaxed">
                Type a topic in the input below, then click a study action — or just ask a question.
              </p>
            </div>
          </div>
        )}

        {messages.map((msg, i) => {
          const isLast = i === messages.length - 1;

          if (msg.role === 'action-result') {
            return (
              <div key={i} className="space-y-2">
                <div className="inline-flex items-center gap-1.5">
                  <span className="chip" style={{ border: '1px solid currentColor' }}>
                    {msg.action.replace('_', ' ')}
                  </span>
                  <span className="font-mono text-[11px] opacity-60 truncate max-w-48">{msg.query}</span>
                </div>
                <div className="b-thin rounded-lg p-4">
                  <StudyOutput
                    result={msg.result}
                    courseId={courseId}
                    onOralFollowUp={(query) => handleAction('oral', query)}
                  />
                </div>

                {/* Suggested next actions — only on last result */}
                {isLast && (
                  <div className="pt-1">
                    <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-2">
                      Suggested next actions
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {NEXT_ACTIONS
                        .filter(n => n.action !== msg.action)
                        .map((n) => (
                          <button
                            key={n.action}
                            onClick={() => handleAction(n.action, msg.query)}
                            disabled={loading}
                            className="btn-ghost text-sm disabled:opacity-40"
                          >
                            {n.glyph} {n.label}
                          </button>
                        ))}
                    </div>
                  </div>
                )}
              </div>
            );
          }

          return (
            <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              <div
                className={`max-w-[85%] rounded-lg px-4 py-3 ${
                  msg.role === 'user'
                    ? 'bg-blue-dark text-white'
                    : 'b-thin bg-white dark:bg-blue-dark/40'
                }`}
              >
                <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                  <div className="mt-3 space-y-2 b-thin-t pt-2">
                    <p className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-70">Sources</p>
                    {msg.citations.map((citation, ci) => (
                      <div key={ci} className="b-thin rounded-md px-3 py-2 bg-white dark:bg-blue-dark/20">
                        <p className="text-xs line-clamp-3 leading-relaxed opacity-90">&ldquo;{citation.snippet}&rdquo;</p>
                        <p className="mt-1 font-mono text-[10px] opacity-60">score · {Math.round(citation.score * 100)}%</p>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {loading && (
          <div className="flex justify-start w-full" aria-live="polite">
            <div className="b-thin rounded-lg px-4 py-3 w-full max-w-[85%] space-y-2">
              <p className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-60 mb-1">
                Retrieving · generating…
              </p>
              <div className="h-1.5 rounded bar-stripes" style={{ background: '#001CE0', opacity: 0.6 }} />
              <div className="h-2 rounded bg-blue-dark/10 animate-pulse w-4/5 mt-1" />
              <div className="h-2 rounded bg-blue-dark/10 animate-pulse w-3/5" />
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Evidence / Inspect drawers */}
      {showEvidence && evidenceCitations.length > 0 && (
        <div className="flex-shrink-0 b-thin-t p-4 max-h-80 overflow-y-auto ws-scroll">
          <EvidenceDrawer citations={evidenceCitations} />
        </div>
      )}
      {showInspect && lastActionResult && (
        <div className="flex-shrink-0 b-thin-t p-4 max-h-64 overflow-y-auto ws-scroll">
          <InspectDrawer msg={lastActionResult} />
        </div>
      )}

      {/* Input area */}
      <div className="flex-shrink-0 b-thin-t p-4">
        {/* Scope chips */}
        <div className="flex items-center gap-2 mb-2">
          <span className="chip text-[10px]" style={{ border: '1px solid currentColor' }}>
            ⌖ scope · all course docs
          </span>
          <span className="chip text-[10px]" style={{ border: '1px solid currentColor' }}>
            k=5 · QVAC
          </span>
          {lastActionResult && (
            <span className="ml-auto font-mono text-[10px] opacity-50">
              {lastActionResult.result.citations.length} sources · {lastActionResult.durationMs != null ? `${lastActionResult.durationMs}ms` : 'done'}
            </span>
          )}
        </div>
        <div className="flex gap-3">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            rows={2}
            disabled={loading}
            className="flex-1 resize-none rounded-md b-thin px-3 py-2 text-sm placeholder-blue-dark/40 dark:placeholder-white/40 bg-transparent outline-none focus:ring-1 focus:ring-blue-dark dark:focus:ring-white disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || loading}
            className="flex-shrink-0 inline-flex items-center justify-center h-10 w-10 self-end btn-primary rounded-lg disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
            </svg>
          </button>
        </div>
        <p className="mt-1.5 font-mono text-[10px] opacity-50">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  );
}
