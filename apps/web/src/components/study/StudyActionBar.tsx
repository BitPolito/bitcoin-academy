'use client';

import type { StudyAction } from '@/lib/api/types';

interface ActionDef {
  id: StudyAction;
  label: string;
  sub: string;
  glyph: string;
  shortcut: string;
}

const ACTIONS: ActionDef[] = [
  { id: 'explain',        label: 'Explain',    sub: 'Step-by-step derivation',          glyph: 'Σ', shortcut: 'E' },
  { id: 'summarize',      label: 'Summarize',  sub: 'Compressed, source-anchored',      glyph: '≡', shortcut: 'S' },
  { id: 'retrieve',       label: 'Retrieve',   sub: 'Top-k from evidence pack',         glyph: '⌖', shortcut: 'R' },
  { id: 'open_questions', label: 'Questions',  sub: 'Conceptual prompts for depth',     glyph: '?', shortcut: 'O' },
  { id: 'quiz',           label: 'Quiz',       sub: 'Multiple-choice with rationale',   glyph: '▢', shortcut: 'Q' },
  { id: 'oral',           label: 'Oral Exam',  sub: 'Adversarial, edge-case driven',    glyph: '◉', shortcut: 'L' },
  { id: 'derive',         label: 'Derive',     sub: 'Proof scaffolding from sources',   glyph: '∂', shortcut: 'D' },
  { id: 'compare',        label: 'Compare',    sub: 'Reconcile across sources',         glyph: '⇌', shortcut: 'C' },
];

interface StudyActionBarProps {
  onAction: (action: StudyAction) => void;
  activeAction: StudyAction | null;
  loading: boolean;
  disabled?: boolean;
  hasIndexedDocs?: boolean;
}

export function StudyActionBar({ onAction, activeAction, loading, disabled, hasIndexedDocs = true }: StudyActionBarProps) {
  const isDisabled = loading || disabled || !hasIndexedDocs;

  return (
    <div className="flex-shrink-0 px-5 py-4 b-thin-b bg-white dark:bg-blue-dark/30">
      <div className="flex items-end justify-between b-thin-b pb-1.5 mb-3">
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">Study action</span>
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-60">⌘E/S/R/O/Q/L/D/C</span>
      </div>
      <div className="grid grid-cols-4 gap-2">
        {ACTIONS.map((a) => {
          const isActive = activeAction === a.id;
          const isRunning = isActive && loading;
          return (
            <button
              key={a.id}
              onClick={() => onAction(a.id)}
              disabled={isDisabled}
              title={hasIndexedDocs ? a.sub : 'Upload documents first'}
              className={`text-left p-2.5 rounded-md transition-all disabled:opacity-40 disabled:cursor-not-allowed ${
                isActive
                  ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                  : 'b-thin hover:bg-blue-dark/5 dark:hover:bg-white/10'
              }`}
            >
              <div className="flex items-center gap-2">
                {isRunning ? (
                  <svg className="w-4 h-4 animate-spin flex-shrink-0" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                  </svg>
                ) : (
                  <span className="mono text-base leading-none w-5 flex-shrink-0">{a.glyph}</span>
                )}
                <span className="text-[12px] font-medium leading-tight truncate">{a.label}</span>
                <span className="ml-auto mono text-[9px] opacity-60 flex-shrink-0">⌘{a.shortcut}</span>
              </div>
              <div className="font-mono text-[10px] opacity-70 mt-1.5 leading-snug">{a.sub}</div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
