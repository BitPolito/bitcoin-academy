'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { getCourse, getCourseLessons, type Course, type Lesson } from '@/lib/services/courses';
import {
  getCourseProgress,
  markLessonComplete,
  type Badge,
  type CourseProgress,
} from '@/lib/services/progress';
import { SplitPane } from '@/components/study/SplitPane';
import { SourcePane } from '@/components/study/SourcePane';
import { OutputPane } from '@/components/study/OutputPane';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { BadgeDisplay } from '@/components/ui/BadgeDisplay';

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

  useEffect(() => {
    async function load() {
      try {
        const [courseData, lessonsData] = await Promise.all([
          getCourse(courseId, accessToken),
          getCourseLessons(courseId, accessToken),
        ]);
        setCourse(courseData);
        setLessons(lessonsData);
        if (lessonsData.length > 0) setSelectedLesson(lessonsData[0]);
      } catch {
        // empty state shown in SourcePane
      } finally {
        setLoading(false);
      }
    }

    async function loadProgress() {
      if (!accessToken) return;
      try {
        const progress = await getCourseProgress(courseId, accessToken);
        setCourseProgress(progress);
      } catch {
        // progress is non-critical
      }
    }

    if (courseId) {
      load();
      loadProgress();
    }
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
      } catch {
        // non-critical; UI stays responsive
      }
    },
    [courseId, accessToken]
  );

  if (loading) {
    return (
      <div className="h-[calc(100vh-7rem)] flex items-center justify-center">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-orange-600" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-7rem)]">
      {/* Course progress strip */}
      {courseProgress && (
        <div className="flex-shrink-0 px-6 py-2 bg-white border-b border-gray-100">
          <ProgressBar
            percent={courseProgress.percent}
            label={`${courseProgress.completedCount} of ${courseProgress.lessonCount} lessons completed`}
            size="sm"
          />
        </div>
      )}

      {/* Badge notification — auto-dismisses after 5 s */}
      {newBadges.length > 0 && (
        <div className="flex-shrink-0 flex items-center gap-3 px-6 py-3 bg-yellow-50 border-b border-yellow-200">
          <span className="text-sm font-medium text-yellow-800">
            {newBadges.length === 1 ? 'New badge earned!' : 'New badges earned!'}
          </span>
          <div className="flex gap-2">
            {newBadges.map((badge) => (
              <BadgeDisplay key={badge.id} badge={badge} size="sm" />
            ))}
          </div>
        </div>
      )}

      {/* Split pane — fills remaining height */}
      <div className="flex-1 overflow-hidden">
        <SplitPane
          left={
            <SourcePane
              courseTitle={course?.title}
              lessons={lessons}
              selectedLesson={selectedLesson}
              completedLessons={completedLessons}
              onSelectLesson={setSelectedLesson}
              onMarkComplete={handleMarkComplete}
            />
          }
          right={
            <OutputPane
              courseId={courseId}
              accessToken={accessToken}
              selectedLesson={selectedLesson}
            />
          }
          defaultLeftPercent={40}
        />
      </div>
    </div>
  );
}
