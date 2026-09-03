'use client';

import { useEffect, useState } from 'react';
import { useSession } from 'next-auth/react';
import { useRouter } from 'next/navigation';
import {
  getCoursesPage,
  createCourse,
  COURSES_PAGE_SIZE,
  type Course,
} from '@/lib/services/courses';
import { getDocumentListRows } from '@/lib/api/documents';
import { CourseCard } from '@/components/courses/CourseCard';
import { CreateCourseModal } from '@/components/courses/CreateCourseModal';

type Filter = 'all';

interface DocStats {
  total: number;
  ready: number;
  processing: number;
  error: number;
}

async function loadDocumentStats(data: Course[], token?: string) {
  const docsResults = await Promise.allSettled(
    data.map((course) => getDocumentListRows(String(course.id), token))
  );
  const statsMap: Record<string | number, DocStats> = {};
  let docs = 0;
  let indexed = 0;
  let processing = 0;
  docsResults.forEach((result, index) => {
    if (result.status !== 'fulfilled') return;
    const rows = result.value;
    const stats: DocStats = {
      total: rows.length,
      ready: rows.filter((row) => row.status === 'ready').length,
      processing: rows.filter((row) => row.status === 'processing' || row.status === 'uploading')
        .length,
      error: rows.filter((row) => row.status === 'error').length,
    };
    statsMap[data[index].id] = stats;
    docs += stats.total;
    indexed += stats.ready;
    processing += stats.processing;
  });
  return { statsMap, totals: { docs, indexed, processing } };
}

export default function CoursesPage() {
  const { data: session, status } = useSession();
  const router = useRouter();
  const [courses, setCourses] = useState<Course[]>([]);
  const [docStats, setDocStats] = useState<Record<string | number, DocStats>>({});
  const [globalStats, setGlobalStats] = useState({ docs: 0, indexed: 0, processing: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [_filter] = useState<Filter>('all');
  const [showCreate, setShowCreate] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key === 'n') {
        e.preventDefault();
        setShowCreate(true);
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  useEffect(() => {
    if (status === 'unauthenticated') {
      router.push('/login');
      return;
    }
    if (status !== 'authenticated') return;

    const token = session?.user?.accessToken;

    async function fetchAll() {
      try {
        const page = await getCoursesPage(undefined, COURSES_PAGE_SIZE, token);
        setCourses(page.items);
        setNextCursor(page.next_cursor);
        const { statsMap, totals } = await loadDocumentStats(page.items, token);
        setDocStats(statsMap);
        setGlobalStats(totals);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load courses');
      } finally {
        setLoading(false);
      }
    }
    fetchAll();
  }, [status, session, router]);

  async function loadMoreCourses() {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    try {
      const token = session?.user?.accessToken;
      const page = await getCoursesPage(nextCursor, COURSES_PAGE_SIZE, token);
      const { statsMap, totals } = await loadDocumentStats(page.items, token);
      setCourses((current) => [...current, ...page.items]);
      setDocStats((current) => ({ ...current, ...statsMap }));
      setGlobalStats((current) => ({
        docs: current.docs + totals.docs,
        indexed: current.indexed + totals.indexed,
        processing: current.processing + totals.processing,
      }));
      setNextCursor(page.next_cursor);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load more courses');
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleCreate(title: string, description?: string) {
    const created = await createCourse(title, description);
    setCourses((prev) => [...prev, created]);
    router.push(`/courses/${created.id}`);
  }

  if (status === 'loading' || (status === 'authenticated' && loading)) {
    return (
      <main className="page-fade max-w-8xl mx-auto px-6 py-8">
        <div className="animate-pulse space-y-8">
          <div className="h-10 w-1/2 bg-blue-dark/10 rounded" />
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {[1, 2, 3].map((i) => (
              <div key={i} className="b-hard rounded-lg p-5 space-y-4" style={{ minHeight: 238 }}>
                <div className="h-3 w-1/3 bg-blue-dark/10 rounded" />
                <div className="h-20 bg-blue-dark/5 rounded" />
                <div className="h-5 w-3/4 bg-blue-dark/10 rounded" />
              </div>
            ))}
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="page-fade max-w-8xl mx-auto px-6 py-8">
      {/* Hero */}
      <div className="grid grid-cols-12 gap-6 mb-10">
        <div className="col-span-12 lg:col-span-8">
          <div className="flex items-center gap-2 font-mono text-[11px] tracking-[0.12em] uppercase opacity-70 mb-6">
            <span>Academy</span>
            <span className="opacity-40">/</span>
            <span className="font-semibold opacity-100">Courses</span>
          </div>
          <h1 className="text-5xl lg:text-6xl font-medium tracking-tight leading-[1.05] mb-5">
            Study, grounded in your
            <br className="hidden lg:block" /> own course material.
          </h1>
          <p className="text-lg leading-relaxed max-w-[58ch] opacity-80">
            Each course is an isolated workspace. Drop in slides, notes and past exams — Academy
            indexes everything and keeps every answer anchored to its source.
          </p>
          <div className="flex items-center gap-3 mt-6">
            <span className="font-mono text-[11px] opacity-60">
              {courses.length} {courses.length === 1 ? 'course' : 'courses'} · {globalStats.docs}{' '}
              documents · {globalStats.indexed} indexed
            </span>
          </div>
        </div>

        {/* Stats widget */}
        <div className="col-span-12 lg:col-span-4">
          <div className="b-hard rounded-lg p-5 bg-white dark:bg-blue-dark/40 tick-corners">
            <div className="flex items-end justify-between b-thin-b pb-1.5 mb-3">
              <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">
                Local index · QVAC
              </span>
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-60">
                v0.1 MVP
              </span>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <StatBox n={String(courses.length)} k="courses" />
              <StatBox n={String(globalStats.docs)} k="documents" />
              <StatBox n={String(globalStats.indexed)} k="indexed" />
              <StatBox
                n={String(globalStats.processing)}
                k="processing"
                warn={globalStats.processing > 0}
              />
            </div>
            <div className="mt-4 pt-4 b-thin-t flex items-center justify-between">
              <span className="font-mono text-[11px] opacity-70">
                Local-first · all data on device
              </span>
              <span className="font-mono text-[10px] tracking-[0.2em] uppercase">v0.1</span>
            </div>
          </div>
        </div>
      </div>

      {/* Filter rail */}
      <div className="flex items-center gap-2 mb-4">
        <button className="font-mono text-[11px] tracking-[0.18em] uppercase px-3 h-8 rounded-md bg-blue-dark text-white dark:bg-white dark:text-blue-dark">
          All <span className="opacity-60 ml-1">{courses.length}</span>
        </button>
        <div className="ml-auto font-mono text-[11px] opacity-60">sorted · stable order</div>
      </div>

      {error ? (
        <div
          className="b-hard rounded-lg p-6 text-center"
          style={{ borderColor: '#b3261e', color: '#b3261e' }}
        >
          <p className="text-sm">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-3 text-sm font-medium underline"
          >
            Retry
          </button>
        </div>
      ) : courses.length === 0 ? (
        <div className="b-hard rounded-lg p-10 text-center bg-white dark:bg-blue-dark">
          <div className="mx-auto w-10 h-10 b-thin rounded-md mb-4 stripes" />
          <div className="font-medium text-lg mb-1">Crea il tuo primo corso</div>
          <div className="opacity-70 text-sm mt-1 mb-6 max-w-xs mx-auto leading-relaxed">
            Ogni corso è un workspace isolato. Carica slide, appunti e dispense — Academy indicizza
            tutto e mantiene ogni risposta ancorata alla fonte.
          </div>
          <div className="flex items-center justify-center gap-3">
            <button className="btn-primary" onClick={() => setShowCreate(true)}>
              Crea il tuo primo corso →
            </button>
            <span className="font-mono text-[11px] opacity-50">⌘N</span>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {courses.map((course) => (
            <CourseCard key={course.id} course={course} stats={docStats[course.id] ?? null} />
          ))}
          {/* Create course card */}
          <button
            onClick={() => setShowCreate(true)}
            className="b-hard rounded-lg p-6 stripes hover-card flex flex-col items-center justify-center min-h-[238px] text-center w-full"
          >
            <div className="font-mono text-3xl leading-none mb-2">+</div>
            <div className="font-medium">Create new course</div>
            <div className="font-mono text-[11px] opacity-70 mt-1">⌘N</div>
          </button>
          {nextCursor && (
            <div className="md:col-span-2 xl:col-span-3 flex justify-center pt-2">
              <button className="btn-ghost" onClick={loadMoreCourses} disabled={loadingMore}>
                {loadingMore ? 'Loading…' : 'Load more courses'}
              </button>
            </div>
          )}
        </div>
      )}

      {showCreate && (
        <CreateCourseModal onClose={() => setShowCreate(false)} onCreate={handleCreate} />
      )}
    </main>
  );
}

function StatBox({ n, k, warn }: { n: string; k: string; warn?: boolean }) {
  return (
    <div className="b-thin rounded-md p-3">
      <div
        className={`text-2xl font-medium tnum ${warn ? '' : ''}`}
        style={warn ? { color: '#a55a00' } : {}}
      >
        {n}
      </div>
      <div className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-70 mt-1">{k}</div>
    </div>
  );
}
