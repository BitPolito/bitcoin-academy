'use client';

import type { StudyAction } from '@/lib/api/types';

interface ActionDef {
  id: StudyAction;
  label: string;
  description: string;
}

const ACTIONS: ActionDef[] = [
  { id: 'explain',        label: 'Explain',    description: 'Explain a concept from course materials' },
  { id: 'summarize',      label: 'Summarize',  description: 'Summarize a topic or section' },
  { id: 'retrieve',       label: 'Sources',    description: 'Find relevant passages' },
  { id: 'open_questions', label: 'Questions',  description: 'Generate open-ended study questions' },
  { id: 'quiz',           label: 'Quiz',       description: 'Generate multiple-choice questions' },
  { id: 'oral',           label: 'Oral Exam',  description: 'Generate oral exam questions' },
];

interface StudyActionBarProps {
  onAction: (action: StudyAction) => void;
  activeAction: StudyAction | null;
  loading: boolean;
  disabled?: boolean;
}

export function StudyActionBar({ onAction, activeAction, loading, disabled }: StudyActionBarProps) {
  return (
    <div className="flex flex-wrap gap-1.5 px-4 py-3 border-b border-gray-100 bg-gray-50">
      {ACTIONS.map((a) => {
        const isActive = activeAction === a.id;
        return (
          <button
            key={a.id}
            onClick={() => onAction(a.id)}
            disabled={loading || disabled}
            title={a.description}
            className={`inline-flex items-center px-3 py-1 rounded-full text-xs font-medium transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-500 disabled:opacity-40 disabled:cursor-not-allowed ${
              isActive
                ? 'bg-orange-600 text-white'
                : 'bg-white text-gray-700 border border-gray-300 hover:border-orange-400 hover:text-orange-600'
            }`}
          >
            {isActive && loading ? (
              <svg className="mr-1 h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
            ) : null}
            {a.label}
          </button>
        );
      })}
    </div>
  );
}
