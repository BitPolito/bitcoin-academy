'use client';

import Link from 'next/link';
import type { Course } from '@/lib/services/courses';

interface DocStats {
  total: number;
  ready: number;
  processing: number;
  error: number;
}

interface CourseCardProps {
  course: Course;
  progress?: number | null;
  stats?: DocStats | null;
}

function Mini({ n, k, warn }: { n: number; k: string; warn?: boolean }) {
  return (
    <div className="text-center">
      <div className="text-xl tnum font-medium" style={warn ? { color: '#a55a00' } : {}}>{n}</div>
      <div className="font-mono text-[9px] tracking-[0.18em] uppercase opacity-70 mt-0.5">{k}</div>
    </div>
  );
}

export function CourseCard({ course, progress = null, stats = null }: CourseCardProps) {
  const failed = stats?.error ?? 0;
  const processing = stats?.processing ?? 0;
  const statusDot =
    failed > 0     ? { color: '#b3261e', label: `${failed} failed` }
    : processing > 0 ? { color: '#a55a00', label: `${processing} processing` }
    : stats        ? { color: '#1a7f3a', label: 'all indexed' }
    : { color: '#1a7f3a', label: progress === 100 ? 'completed' : progress != null && progress > 0 ? `${progress}% done` : 'ready' };

  return (
    <Link
      href={`/courses/${course.id}`}
      className="b-hard rounded-lg p-5 bg-white dark:bg-blue-dark/30 hover-card cursor-pointer block"
    >
      {/* Top row */}
      <div className="flex items-center justify-between mb-3">
        <span className="font-mono text-[10px] tracking-[0.2em] uppercase opacity-70">
          {course.description ? course.description.slice(0, 20) : `#${course.id}`}
        </span>
      </div>

      {/* Striped cover */}
      <div className="stripes b-thin rounded-md mb-4 relative overflow-hidden" style={{ aspectRatio: '16/7' }}>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-50">
            {course.title.slice(0, 16)}
          </span>
        </div>
        <div className="absolute top-1.5 left-1.5 w-2 h-2 border-l border-t border-current opacity-40" />
        <div className="absolute top-1.5 right-1.5 w-2 h-2 border-r border-t border-current opacity-40" />
        <div className="absolute bottom-1.5 left-1.5 w-2 h-2 border-l border-b border-current opacity-40" />
        <div className="absolute bottom-1.5 right-1.5 w-2 h-2 border-r border-b border-current opacity-40" />
      </div>

      <h3 className="text-lg font-medium leading-snug mb-1">{course.title}</h3>
      {course.description && (
        <div className="font-mono text-[11px] opacity-70 mb-3 line-clamp-1">{course.description}</div>
      )}

      {/* Doc stats grid */}
      {stats && (
        <div className="grid grid-cols-3 gap-2 mb-4">
          <Mini n={stats.total}      k="docs"    />
          <Mini n={stats.ready}      k="indexed" />
          <Mini n={processing + failed} k="open" warn={failed > 0 || processing > 0} />
        </div>
      )}

      {/* Footer */}
      <div className="flex items-center justify-between b-thin-t pt-3 mt-auto">
        <span className="font-mono text-[11px] flex items-center gap-2">
          <span className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0" style={{ background: statusDot.color }} />
          {statusDot.label}
        </span>
        {progress != null && progress > 0 && progress < 100 && (
          <span className="font-mono text-[11px] opacity-60">{progress}% done</span>
        )}
      </div>
    </Link>
  );
}
