'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { getCourse, getCourseLessons, type Course, type Lesson } from '@/lib/services/courses';
import { getDocumentListRows } from '@/lib/api/documents';
import {
  getCourseProgress,
  markLessonComplete,
  type Badge,
  type CourseProgress,
} from '@/lib/services/progress';
import { SplitPane } from '@/components/study/SplitPane';
import { SourcePane } from '@/components/study/SourcePane';
import { OutputPane } from '@/components/study/OutputPane';
import { BadgeDisplay } from '@/components/ui/BadgeDisplay';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';

export default function StudyPage() {
  const params = useParams();
  const courseId = params.courseId as string;
  const { data: session } = useSession();
  const accessToken = (session?.user as any)?.accessToken;

  const [course, setCourse] = useState<Course | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [selectedLesson, setSelectedLesson] = useState<Lesson | null>(null);
  const [completedLessons, setCompletedLessons] = useState<Set<string>>(new Set());
  const [courseProgress, setCourseProgress] = useState<CourseProgress | null>(null);
  const [newBadges, setNewBadges] = useState<Badge[]>([]);
  const [loading, setLoading] = useState(true);
  const [hasIndexedDocs, setHasIndexedDocs] = useState(false);

  useEffect(() => {
    async function load() {
      try {
        const [courseData, lessonsData, docs] = await Promise.all([
          getCourse(courseId, accessToken),
          getCourseLessons(courseId, accessToken),
          getDocumentListRows(courseId, accessToken),
        ]);
        setCourse(courseData);
        setLessons(lessonsData);
        if (lessonsData.length > 0) setSelectedLesson(lessonsData[0]);
        setHasIndexedDocs(docs.some((d) => d.status === 'ready'));
      } catch {
        // empty state shown in SourcePane
      } finally {
        setLoading(false);
      }
    }

    async function loadProgress() {
      if (!accessToken) return;
      try {
        const p = await getCourseProgress(courseId, accessToken);
        setCourseProgress(p);
        if (p.completedLessonIds.length > 0) {
          setCompletedLessons(new Set(p.completedLessonIds));
        }
      } catch { /* non-critical */ }
    }

    if (courseId) { load(); loadProgress(); }
  }, [courseId, accessToken]);

  const handleMarkComplete = useCallback(
    async (lesson: Lesson) => {
      if (!accessToken) return;
      const lessonId = String(lesson.id);
      try {
        const result = await markLessonComplete(lessonId, courseId, accessToken);
        setCompletedLessons((prev) => new Set([...prev, lessonId]));
        setCourseProgress(result.courseProgress);
        if (result.newBadges.length > 0) {
          setNewBadges(result.newBadges);
          setTimeout(() => setNewBadges([]), 5000);
        }
      } catch { /* non-critical */ }
    },
    [courseId, accessToken]
  );

  if (loading) {
    return (
      <div className="h-[calc(100vh-3.5rem)] flex items-center justify-center">
        <div className="space-y-2 text-center">
          <div className="w-8 h-8 border-2 border-blue-dark/30 border-t-blue-dark rounded-full animate-spin mx-auto" />
          <p className="font-mono text-[11px] tracking-[0.18em] uppercase opacity-60">Loading…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* Progress strip */}
      {courseProgress && (
        <div className="flex-shrink-0 px-6 py-2 bg-white b-thin-b flex items-center gap-4">
          <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-70 whitespace-nowrap">
            Progress
          </span>
          <div className="flex-1 h-1.5 b-thin overflow-hidden rounded-none">
            <div
              className="h-full bg-blue-dark transition-all"
              style={{ width: `${courseProgress.percent}%` }}
            />
          </div>
          <span className="font-mono text-[11px] opacity-60 whitespace-nowrap">
            {courseProgress.completedCount}/{courseProgress.lessonCount}
          </span>
        </div>
      )}

      {/* Badge notification */}
      {newBadges.length > 0 && (
        <div className="flex-shrink-0 flex items-center gap-3 px-6 py-2 b-thin-b bg-white">
          <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-70">
            {newBadges.length === 1 ? 'Badge earned' : 'Badges earned'}
          </span>
          <div className="flex gap-2">
            {newBadges.map((badge) => (
              <BadgeDisplay key={badge.id} badge={badge} size="sm" />
            ))}
          </div>
        </div>
      )}

      {/* Split pane */}
      <div className="flex-1 overflow-hidden">
        <SplitPane
          left={
            <SourcePane
              courseId={courseId}
              accessToken={accessToken}
              courseTitle={course?.title}
              lessons={lessons}
              selectedLesson={selectedLesson}
              completedLessons={completedLessons}
              onSelectLesson={setSelectedLesson}
              onMarkComplete={handleMarkComplete}
            />
          }
          right={
            <ErrorBoundary>
              <OutputPane
                courseId={courseId}
                accessToken={accessToken}
                selectedLesson={selectedLesson}
                hasIndexedDocs={hasIndexedDocs}
              />
            </ErrorBoundary>
          }
          defaultLeftPercent={40}
        />
      </div>
    </div>
  );
}
