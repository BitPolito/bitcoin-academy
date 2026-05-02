'use client';

import type { Lesson } from '@/lib/services/courses';

interface LessonNavProps {
  lessons: Lesson[];
  selectedLesson: Lesson | null;
  completedLessons: Set<string>;
  onSelect: (lesson: Lesson) => void;
  loading?: boolean;
}

export function LessonNav({
  lessons,
  selectedLesson,
  completedLessons,
  onSelect,
  loading = false,
}: LessonNavProps) {
  if (loading) {
    return (
      <div className="space-y-1 p-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 bg-gray-100 rounded animate-pulse" />
        ))}
      </div>
    );
  }

  if (lessons.length === 0) {
    return (
      <div className="px-4 py-6 text-center text-sm text-gray-400">
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

          return (
            <li key={lesson.id}>
              <button
                onClick={() => onSelect(lesson)}
                className={`w-full flex items-center gap-3 px-4 py-3 text-left transition-colors border-l-2 ${
                  isSelected
                    ? 'border-orange-500 bg-orange-50 text-orange-700'
                    : 'border-transparent hover:bg-gray-50 text-gray-700'
                }`}
                aria-current={isSelected ? 'true' : undefined}
              >
                <span
                  className={`flex-shrink-0 flex items-center justify-center h-6 w-6 rounded-full text-xs font-semibold ${
                    isCompleted
                      ? 'bg-green-100 text-green-700'
                      : isSelected
                      ? 'bg-orange-100 text-orange-700'
                      : 'bg-gray-100 text-gray-500'
                  }`}
                  aria-hidden="true"
                >
                  {isCompleted ? (
                    <svg
                      className="h-3.5 w-3.5"
                      fill="none"
                      viewBox="0 0 24 24"
                      strokeWidth={2.5}
                      stroke="currentColor"
                    >
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                    </svg>
                  ) : (
                    index + 1
                  )}
                </span>
                <span className="flex-1 min-w-0 text-sm font-medium truncate">
                  {lesson.title}
                </span>
                {isCompleted && (
                  <span className="flex-shrink-0 text-xs text-green-600 font-medium">Done</span>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
