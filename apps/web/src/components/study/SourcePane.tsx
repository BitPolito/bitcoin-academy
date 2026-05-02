'use client';

import { LessonNav } from './LessonNav';
import { ContentChunks } from './ContentChunks';
import type { Lesson } from '@/lib/services/courses';

interface SourcePaneProps {
  courseId: string;
  accessToken?: string;
  courseTitle?: string;
  lessons: Lesson[];
  selectedLesson: Lesson | null;
  completedLessons: Set<string>;
  onSelectLesson: (lesson: Lesson) => void;
  onMarkComplete: (lesson: Lesson) => Promise<void>;
  loadingLessons?: boolean;
}

export function SourcePane({
  courseId,
  accessToken,
  courseTitle,
  lessons,
  selectedLesson,
  completedLessons,
  onSelectLesson,
  onMarkComplete,
  loadingLessons = false,
}: SourcePaneProps) {
  const isCompleted = selectedLesson
    ? completedLessons.has(String(selectedLesson.id))
    : false;

  return (
    <div className="h-full flex flex-col bg-white dark:bg-blue-dark/30">
      {/* Header */}
      <div className="flex-shrink-0 px-5 py-3 b-thin-b flex items-center gap-3">
        <span className="mono text-[10px] tracking-[0.22em] uppercase opacity-70">Source</span>
        {courseTitle && (
          <span className="font-medium text-sm truncate">{courseTitle}</span>
        )}
      </div>

      {/* Lesson nav */}
      <div className="flex-shrink-0 b-thin-b overflow-y-auto max-h-52 ws-scroll">
        <LessonNav
          lessons={lessons}
          selectedLesson={selectedLesson}
          completedLessons={completedLessons}
          onSelect={onSelectLesson}
          loading={loadingLessons}
        />
      </div>

      {/* Lesson content */}
      <div className="flex-1 overflow-y-auto ws-scroll">
        {selectedLesson ? (
          <div className="p-5 space-y-4">
            <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">
              Lesson {selectedLesson.id}
            </div>
            <h3 className="text-xl font-medium leading-snug">{selectedLesson.title}</h3>

            {selectedLesson.content && (
              <p className="text-[13.5px] leading-relaxed opacity-90 whitespace-pre-wrap">
                {selectedLesson.content}
              </p>
            )}

            <ContentChunks courseId={courseId} accessToken={accessToken} className="mt-2" />

            <div className="pt-2 b-thin-t">
              {isCompleted ? (
                <div className="flex items-center gap-2 font-mono text-[11px]" style={{ color: '#1a7f3a' }}>
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  Lesson completed
                </div>
              ) : (
                <button
                  onClick={() => onMarkComplete(selectedLesson)}
                  className="btn-ghost text-sm"
                >
                  Mark as complete
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full p-8">
            <div className="text-center">
              <div className="mx-auto w-10 h-10 b-thin rounded-md mb-4 stripes" />
              <p className="font-mono text-[11px] opacity-60">Select a lesson to begin.</p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
