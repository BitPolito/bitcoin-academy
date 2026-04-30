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
    <div className="h-full flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 px-6 py-4 border-b border-gray-200 bg-white">
        <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide">
          Study Path
        </h2>
        {courseTitle && (
          <p className="mt-0.5 text-xs text-gray-500">{courseTitle}</p>
        )}
      </div>

      {/* Lesson list — capped height so content is still visible */}
      <div className="flex-shrink-0 border-b border-gray-200 overflow-y-auto max-h-56 bg-white">
        <LessonNav
          lessons={lessons}
          selectedLesson={selectedLesson}
          completedLessons={completedLessons}
          onSelect={onSelectLesson}
          loading={loadingLessons}
        />
      </div>

      {/* Lesson content */}
      <div className="flex-1 overflow-y-auto bg-gray-50">
        {selectedLesson ? (
          <div className="p-6 space-y-4">
            <h3 className="text-base font-semibold text-gray-900">
              {selectedLesson.title}
            </h3>

            {selectedLesson.content && (
              <p className="text-sm text-gray-700 leading-relaxed whitespace-pre-wrap">
                {selectedLesson.content}
              </p>
            )}

            {/* Document chunks from uploaded course material */}
            <ContentChunks
              courseId={courseId}
              accessToken={accessToken}
              className="mt-2"
            />

            {/* Completion button */}
            <div className="pt-2">
              {isCompleted ? (
                <div className="flex items-center gap-2 text-sm text-green-600 font-medium">
                  <svg
                    className="h-4 w-4"
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2.5}
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
                  </svg>
                  Lesson completed
                </div>
              ) : (
                <button
                  onClick={() => onMarkComplete(selectedLesson)}
                  className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-orange-600 rounded-md hover:bg-orange-700 transition-colors focus:outline-none focus:ring-2 focus:ring-orange-500 focus:ring-offset-2"
                >
                  Mark as complete
                </button>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full p-8">
            <div className="text-center max-w-sm">
              <svg
                className="mx-auto h-12 w-12 text-gray-300"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M4.26 10.147a60.438 60.438 0 00-.491 6.347A48.62 48.62 0 0112 20.904a48.62 48.62 0 018.232-4.41 60.46 60.46 0 00-.491-6.347m-15.482 0a50.636 50.636 0 00-2.658-.813A59.906 59.906 0 0112 3.493a59.903 59.903 0 0110.399 5.84c-.896.248-1.783.52-2.658.814m-15.482 0A50.717 50.717 0 0112 13.489a50.702 50.702 0 017.74-3.342"
                />
              </svg>
              <h3 className="mt-4 text-sm font-medium text-gray-900">
                Select a lesson to begin
              </h3>
              <p className="mt-1 text-sm text-gray-500">
                Choose a lesson from the list above to view its content and start studying.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
