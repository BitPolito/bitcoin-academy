'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import type { ApiStudyResponse, StudyAction } from '@/lib/api/types';
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
import { Spinner } from '@/components/ui/Spinner';
import { issueCertificate, type Certificate } from '@/lib/services/certificates';
import { fetchHealthStatus } from '@/lib/services/health';

export default function StudyPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const courseId = params.courseId as string;
  const { data: session } = useSession();
  const accessToken = session?.user?.accessToken;

  const initialQuery = searchParams.get('q') ?? '';
  const initialAction = (searchParams.get('action') as StudyAction) || null;

  const [course, setCourse] = useState<Course | null>(null);
  const [lessons, setLessons] = useState<Lesson[]>([]);
  const [selectedLesson, setSelectedLesson] = useState<Lesson | null>(null);
  const [completedLessons, setCompletedLessons] = useState<Set<string>>(new Set());
  const [courseProgress, setCourseProgress] = useState<CourseProgress | null>(null);
  const [newBadges, setNewBadges] = useState<Badge[]>([]);
  const [certificate, setCertificate] = useState<Certificate | null>(null);
  const [certLoading, setCertLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [hasIndexedDocs, setHasIndexedDocs] = useState(false);
  const [lastActionResult, setLastActionResult] = useState<{
    result: ApiStudyResponse;
    lesson: Lesson | null;
  } | null>(null);
  const [qvacDown, setQvacDown] = useState(false);

  const activeCitationDocIds = useMemo(() => {
    if (!lastActionResult) return new Set<string>();
    return new Set(
      lastActionResult.result.citations.map((c) => c.doc_id).filter(Boolean) as string[]
    );
  }, [lastActionResult]);

  const lastStudiedLessonId = lastActionResult?.lesson ? String(lastActionResult.lesson.id) : null;

  const handleActionResult = useCallback((result: ApiStudyResponse, lesson: Lesson | null) => {
    setLastActionResult({ result, lesson });
  }, []);

  // Poll /health every 30 s; show banner when QVAC is unreachable.
  useEffect(() => {
    let cancelled = false;
    async function check() {
      try {
        const h = await fetchHealthStatus();
        if (!cancelled) setQvacDown(h.qvac === 'unreachable');
      } catch {
        if (!cancelled) setQvacDown(true);
      }
    }
    check();
    const id = setInterval(check, 30_000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

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
      } catch {
        /* non-critical */
      }
    }

    if (courseId) {
      load();
      loadProgress();
    }
  }, [courseId, accessToken]);

  const handleClaimCertificate = useCallback(async () => {
    if (!accessToken || certLoading) return;
    setCertLoading(true);
    try {
      const cert = await issueCertificate(courseId, accessToken);
      setCertificate(cert);
    } catch {
      /* non-critical */
    } finally {
      setCertLoading(false);
    }
  }, [courseId, accessToken, certLoading]);

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
        /* non-critical */
      }
    },
    [courseId, accessToken]
  );

  if (loading) {
    return (
      <div className="h-[calc(100vh-3.5rem)] flex items-center justify-center">
        <Spinner size="md" label="Loading…" />
      </div>
    );
  }

  return (
    <div className="flex flex-col h-[calc(100vh-3.5rem)]">
      {/* QVAC unavailable banner */}
      {qvacDown && (
        <div
          className="flex-shrink-0 flex items-center gap-3 px-6 py-2 font-mono text-[11px]"
          style={{ background: '#a55a0015', borderBottom: '1px solid #a55a0040', color: '#a55a00' }}
          role="alert"
        >
          <span
            className="inline-block w-1.5 h-1.5 rounded-full flex-shrink-0"
            style={{ background: '#a55a00' }}
          />
          Servizio AI temporaneamente non disponibile — le risposte potrebbero essere incomplete.
        </div>
      )}

      {/* Progress strip */}
      {courseProgress && (
        <div className="flex-shrink-0 px-6 py-2 bg-white b-thin-b flex items-center gap-4">
          <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-70 whitespace-nowrap">
            Progress
          </span>
          <div className="flex-1 h-1.5 b-thin overflow-hidden rounded-none">
            <div
              role="progressbar"
              aria-valuenow={courseProgress.percent}
              aria-valuemin={0}
              aria-valuemax={100}
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

      {/* Certificate CTA — shown when course is 100% complete */}
      {courseProgress?.percent === 100 && !certificate && (
        <div className="flex-shrink-0 flex items-center gap-4 px-6 py-2.5 b-thin-b bg-white dark:bg-blue-dark/20">
          <svg className="w-4 h-4 flex-shrink-0 opacity-70" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z" />
          </svg>
          <span className="font-mono text-[11px] tracking-[0.14em] uppercase opacity-80 flex-1">
            Corso completato — ottieni il tuo certificato
          </span>
          <button
            onClick={handleClaimCertificate}
            disabled={certLoading}
            className="btn-primary text-sm py-1 px-3 disabled:opacity-60"
          >
            {certLoading ? 'Generazione…' : 'Ottieni certificato'}
          </button>
        </div>
      )}

      {/* Certificate issued confirmation */}
      {certificate && (
        <div className="flex-shrink-0 flex items-center gap-4 px-6 py-2.5 b-thin-b bg-white dark:bg-blue-dark/20">
          <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.5} style={{ color: '#1a7f3a' }}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M9 12.75L11.25 15 15 9.75M21 12c0 1.268-.63 2.39-1.593 3.068a3.745 3.745 0 01-1.043 3.296 3.745 3.745 0 01-3.296 1.043A3.745 3.745 0 0112 21c-1.268 0-2.39-.63-3.068-1.593a3.746 3.746 0 01-3.296-1.043 3.745 3.745 0 01-1.043-3.296A3.745 3.745 0 013 12c0-1.268.63-2.39 1.593-3.068a3.745 3.745 0 011.043-3.296 3.746 3.746 0 013.296-1.043A3.746 3.746 0 0112 3c1.268 0 2.39.63 3.068 1.593a3.746 3.746 0 013.296 1.043 3.746 3.746 0 011.043 3.296A3.745 3.745 0 0121 12z" />
          </svg>
          <span className="font-mono text-[11px] tracking-[0.14em] uppercase flex-1" style={{ color: '#1a7f3a' }}>
            Certificato emesso — codice verificabile:
          </span>
          <span className="font-mono text-[12px] font-semibold tracking-widest opacity-80">
            {certificate.code}
          </span>
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
              activeCitationDocIds={activeCitationDocIds}
              lastStudiedLessonId={lastStudiedLessonId}
            />
          }
          right={
            <ErrorBoundary>
              <OutputPane
                courseId={courseId}
                accessToken={accessToken}
                selectedLesson={selectedLesson}
                hasIndexedDocs={hasIndexedDocs}
                initialQuery={initialQuery}
                initialAction={initialAction}
                onActionResult={handleActionResult}
              />
            </ErrorBoundary>
          }
          defaultLeftPercent={40}
        />
      </div>
    </div>
  );
}
