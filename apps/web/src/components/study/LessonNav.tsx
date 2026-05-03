'use client';

import type { Lesson } from '@/lib/services/courses';

interface LessonNavProps {
  lessons: Lesson[];
  selectedLesson: Lesson | null;
  completedLessons: Set<string>;
  onSelect: (lesson: Lesson) => void;
  loading?: boolean;
  studiedLessonId?: string | null;
}

export function LessonNav({
  lessons,
  selectedLesson,
  completedLessons,
  onSelect,
  loading = false,
  studiedLessonId,
}: LessonNavProps) {
  if (loading) {
    return (
      <div className="space-y-1 p-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-9 bg-blue-dark/5 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  if (lessons.length === 0) {
    return (
      <div className="px-4 py-5 text-center font-mono text-[11px] opacity-50">
        No lessons available yet.
      </div>
    );
  }

  return (
    <nav aria-label="Course lessons">
      <ul>
        {lessons.map((lesson, index) => {
          const lessonId = String(lesson.id);
          const isSelected = selectedLesson?.id === lesson.id;
          const isCompleted = completedLessons.has(lessonId);
          const isStudied = studiedLessonId === lessonId && !isSelected;

          return (
            <li key={lesson.id}>
              <button
                onClick={() => onSelect(lesson)}
                className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors text-[13px] ${
                  isSelected
                    ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                    : 'hover:bg-blue-dark/5 dark:hover:bg-white/10'
                }`}
                aria-current={isSelected ? 'true' : undefined}
              >
                <span
                  className={`flex-shrink-0 flex items-center justify-center h-5 w-5 rounded-sm font-mono text-[10px] font-semibold b-thin ${
                    isCompleted ? 'opacity-60' : ''
                  }`}
                  aria-hidden="true"
                >
                  {isCompleted ? (
                    <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                  ) : (
                    index + 1
                  )}
                </span>
                <span className="flex-1 min-w-0 font-medium truncate">{lesson.title}</span>
                {isStudied && (
                  <span className="flex-shrink-0 inline-block w-1.5 h-1.5 rounded-full bg-blue-dark dark:bg-white opacity-60" title="Last studied" />
                )}
                {isCompleted && (
                  <span className="flex-shrink-0 font-mono text-[9px] tracking-[0.18em] uppercase opacity-60">done</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
