'use client';

import Link from 'next/link';
import type { Course } from '@/lib/services/courses';
import { ProgressBar } from '@/components/ui/ProgressBar';

interface CourseCardProps {
  course: Course;
  progress?: number | null;
}

export function CourseCard({ course, progress = null }: CourseCardProps) {
  const ctaLabel =
    progress === 100
      ? 'Review course'
      : progress != null && progress > 0
      ? 'Continue studying'
      : 'Start studying';

  return (
    <Link
      href={`/courses/${course.id}`}
      className="block bg-white rounded-lg shadow hover:shadow-md transition-shadow border border-gray-100"
    >
      <div className="p-6">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-gray-900 truncate">
              {course.title}
            </h3>
            {course.description && (
              <p className="mt-2 text-sm text-gray-600 line-clamp-2">
                {course.description}
              </p>
            )}
          </div>
          <div className="ml-4 flex-shrink-0">
            <span className="inline-flex items-center justify-center h-10 w-10 rounded-lg bg-orange-100 text-orange-600">
              <svg
                className="h-5 w-5"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={1.5}
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 6.042A8.967 8.967 0 006 3.75c-1.052 0-2.062.18-3 .512v14.25A8.987 8.987 0 016 18c2.305 0 4.408.867 6 2.292m0-14.25a8.966 8.966 0 016-2.292c1.052 0 2.062.18 3 .512v14.25A8.987 8.987 0 0018 18a8.967 8.967 0 00-6 2.292m0-14.25v14.25"
                />
              </svg>
            </span>
          </div>
        </div>

        {/* Progress indicator */}
        <div className="mt-4">
          {progress !== null ? (
            <ProgressBar percent={progress} size="sm" />
          ) : (
            <div className="h-1.5 w-full bg-gray-100 rounded-full animate-pulse" />
          )}
        </div>

        <div className="mt-3 flex items-center text-sm text-orange-600 font-medium">
          {ctaLabel}
          <svg
            className="ml-1 h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
          </svg>
        </div>
      </div>
    </Link>
  );
}
