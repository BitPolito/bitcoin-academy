'use client';

import { useEffect, useRef, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { getCourse, updateCourse, deleteCourse, type Course } from '@/lib/services/courses';
import { DocumentUpload } from '@/components/documents/DocumentUpload';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { getDocumentListRows, deleteDocument, reindexCourse } from '@/lib/api/documents';
import type { DocumentListRow } from '@/lib/api/types';
import { DocumentProcessingPanel } from '@/components/documents/DocumentProcessingPanel';
import { useToast } from '@/components/ui/Toast';
import { EditCourseModal } from '@/components/courses/EditCourseModal';

type DocFilter = 'all' | 'ready' | 'processing' | 'error';

const FILTER_OPTIONS: { id: DocFilter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'ready', label: 'Indexed' },
  { id: 'processing', label: 'Processing' },
  { id: 'error', label: 'Failed' },
];

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const STATE_DOT: Record<string, string> = {
  ready: '#1a7f3a',
  processing: '#a55a00',
  uploading: '#a55a00',
  error: '#b3261e',
};

const LIFECYCLE_STAGES = ['uploading', 'processing', 'ready'] as const;
const PROCESSING_SUBSTAGES = ['parsing', 'chunking', 'indexing'] as const;
const POLL_INTERVAL_MS = 5_000;
const POLL_TIMEOUT_MS = 15 * 60 * 1_000;

function useElapsedMinutes(startIso: string | null): number {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (!startIso) return;
    const tick = () => setElapsed(Math.floor((Date.now() - new Date(startIso).getTime()) / 60_000));
    tick();
    const id = setInterval(tick, 30_000);
    return () => clearInterval(id);
  }, [startIso]);
  return elapsed;
}

function Lifecycle({ status, processingStage, updatedAt }: { status: string; processingStage?: string; updatedAt?: string }) {
  const isActive = status === 'processing' || status === 'uploading';
  const elapsedMin = useElapsedMinutes(isActive ? (updatedAt ?? null) : null);
  const failed = status === 'error';
  const idx = failed ? -1 : (LIFECYCLE_STAGES as readonly string[]).indexOf(status);

  const subIdx = processingStage
    ? (PROCESSING_SUBSTAGES as readonly string[]).indexOf(processingStage)
    : -1;

  return (
    <div>
      {/* Top-level lifecycle: uploading → processing → ready */}
      <div className="flex items-center gap-1.5">
        {LIFECYCLE_STAGES.map((s, i) => {
          const done = !failed && i < idx;
          const here = !failed && i === idx;
          return (
            <div key={s} className="flex items-center gap-1.5 flex-1">
              <div
                className={`flex-1 h-7 b-thin rounded-sm flex items-center justify-center font-mono text-[10px] tracking-[0.16em] uppercase ${
                  done
                    ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                    : here
                      ? 'bg-blue-dark/10'
                      : 'opacity-40'
                }`}
              >
                {s}
              </div>
              {i < LIFECYCLE_STAGES.length - 1 && (
                <span className="opacity-40 mono text-[10px]">›</span>
              )}
            </div>
          );
        })}
        {failed && (
          <span className="ml-2 chip" style={{ color: '#b3261e', border: '1px solid #b3261e' }}>
            FAILED
          </span>
        )}
      </div>

      {/* Sub-stage stepper — visible while processing */}
      {status === 'processing' && (
        <div className="mt-3">
          <div className="flex items-center gap-1">
            {PROCESSING_SUBSTAGES.map((sub, i) => {
              const subDone = i < subIdx;
              const subHere = i === subIdx;
              return (
                <div key={sub} className="flex items-center gap-1 flex-1">
                  <div
                    className={`flex-1 h-5 rounded-sm flex items-center justify-center font-mono text-[9px] tracking-[0.14em] uppercase transition-all ${
                      subDone
                        ? 'bg-blue-dark/60 text-white dark:bg-white/60 dark:text-blue-dark'
                        : subHere
                          ? 'bg-blue-dark/15 dotpulse-border'
                          : 'b-thin opacity-30'
                    }`}
                    style={subHere ? { border: '1px solid rgba(0,28,224,0.35)' } : undefined}
                  >
                    {subHere && (
                      <span
                        className="inline-block w-1 h-1 rounded-full dotpulse mr-1 flex-shrink-0"
                        style={{ background: '#a55a00' }}
                      />
                    )}
                    {sub}
                  </div>
                  {i < PROCESSING_SUBSTAGES.length - 1 && (
                    <span className="opacity-30 mono text-[9px]">›</span>
                  )}
                </div>
              );
            })}
            <div className="flex items-center gap-1 flex-1">
              <span className="opacity-30 mono text-[9px]">›</span>
              <div className="flex-1 h-5 b-thin rounded-sm flex items-center justify-center font-mono text-[9px] tracking-[0.14em] uppercase opacity-30">
                ready
              </div>
            </div>
          </div>
          <div className="mt-1.5 flex items-center gap-2 font-mono text-[10px] opacity-60">
            <span>{processingStage ? processingStage.charAt(0).toUpperCase() + processingStage.slice(1) + '…' : 'Processing…'}</span>
            {elapsedMin > 0 && <span className="opacity-70">· {elapsedMin} min elapsed</span>}
          </div>
        </div>
      )}

      {/* Uploading state */}
      {status === 'uploading' && (
        <div className="mt-2 flex items-center gap-2 font-mono text-[11px] opacity-70">
          <span
            className="inline-block w-1.5 h-1.5 rounded-full dotpulse flex-shrink-0"
            style={{ background: '#a55a00' }}
          />
          <span>Uploading…</span>
          {elapsedMin > 0 && <span className="opacity-60">· {elapsedMin} min</span>}
        </div>
      )}
    </div>
  );
}

export default function CourseWorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.courseId as string;
  const { data: session } = useSession();
  const accessToken = session?.user?.accessToken;

  const { showToast } = useToast();
  const [course, setCourse] = useState<Course | null>(null);
  const [docs, setDocs] = useState<DocumentListRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [docsLoading, setDocsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<DocFilter>('all');
  const [refreshKey, setRefreshKey] = useState(0);
  const [reindexing, setReindexing] = useState(false);
  const [showEdit, setShowEdit] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [pollTimedOut, setPollTimedOut] = useState(false);
  const pollStartRef = useRef<number | null>(null);

  const refreshDocuments = useCallback(() => setRefreshKey((k) => k + 1), []);

  async function handleEdit(title: string, description?: string) {
    const updated = await updateCourse(courseId, title, description, accessToken);
    setCourse(updated);
  }

  async function handleDelete() {
    if (!confirm(`Eliminare il corso "${course?.title}" e tutti i suoi documenti? L'operazione non è reversibile.`)) return;
    setDeleting(true);
    try {
      await deleteCourse(courseId, accessToken);
      router.push('/courses');
    } catch {
      showToast('Impossibile eliminare il corso. Riprova.', 'err');
      setDeleting(false);
    }
  }

  async function handleReindexAll() {
    if (reindexing) return;
    setReindexing(true);
    try {
      const { enqueued, skipped } = await reindexCourse(courseId, accessToken);
      showToast(
        skipped > 0
          ? `Queued ${enqueued} documents (${skipped} skipped — file missing).`
          : `Queued ${enqueued} documents for re-ingestion.`,
        'ok',
      );
      refreshDocuments();
    } catch {
      showToast('Could not start re-indexing. Try again.', 'err');
    } finally {
      setReindexing(false);
    }
  }

  useEffect(() => {
    async function load() {
      try {
        const courseData = await getCourse(courseId, accessToken);
        setCourse(courseData);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load course');
      } finally {
        setLoading(false);
      }
    }
    if (courseId) load();
  }, [courseId, accessToken]);

  useEffect(() => {
    async function loadDocs() {
      try {
        setDocsLoading(true);
        const rows = await getDocumentListRows(courseId, accessToken);
        setDocs(rows);
        if (rows.length > 0 && !selectedId) setSelectedId(rows[0].id);
      } catch {
        setDocs([]);
      } finally {
        setDocsLoading(false);
      }
    }
    if (courseId) loadDocs();
  }, [courseId, accessToken, refreshKey]);

  // Auto-poll every 5s while documents are processing; stop after 15 min.
  useEffect(() => {
    const hasActive = docs.some((d) => d.status === 'processing' || d.status === 'uploading');
    if (!hasActive) {
      pollStartRef.current = null;
      return;
    }
    if (pollTimedOut) return;
    if (pollStartRef.current === null) pollStartRef.current = Date.now();
    const id = setInterval(() => {
      if (Date.now() - (pollStartRef.current ?? Date.now()) >= POLL_TIMEOUT_MS) {
        setPollTimedOut(true);
        clearInterval(id);
        return;
      }
      refreshDocuments();
    }, POLL_INTERVAL_MS);
    return () => clearInterval(id);
  }, [docs, pollTimedOut, refreshDocuments]);

  if (loading) {
    return (
      <main className="page-fade max-w-8xl mx-auto px-6 py-6">
        <div className="animate-pulse space-y-5">
          <div className="b-hard rounded-lg h-24 bg-blue-dark/5" />
          <div className="grid grid-cols-12 gap-5">
            <div className="col-span-7 space-y-3">
              <div className="h-32 b-hard rounded-lg bg-blue-dark/5" />
              <div className="h-64 b-hard rounded-lg bg-blue-dark/5" />
            </div>
            <div className="col-span-5 h-96 b-hard rounded-lg bg-blue-dark/5" />
          </div>
        </div>
      </main>
    );
  }

  if (error || !course) {
    return (
      <main className="max-w-8xl mx-auto px-6 py-6">
        <div
          className="b-hard rounded-lg p-6 text-center"
          style={{ borderColor: '#b3261e', color: '#b3261e' }}
        >
          <p className="text-sm">{error || 'Course not found'}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-3 text-sm font-medium underline"
          >
            Retry
          </button>
        </div>
      </main>
    );
  }

  const indexed = docs.filter((d) => d.status === 'ready').length;
  const processing = docs.filter(
    (d) => d.status === 'processing' || d.status === 'uploading'
  ).length;
  const failed = docs.filter((d) => d.status === 'error').length;

  const filtered = docs.filter((d) => {
    if (filter === 'all') return true;
    if (filter === 'ready') return d.status === 'ready';
    if (filter === 'processing') return d.status === 'processing' || d.status === 'uploading';
    if (filter === 'error') return d.status === 'error';
    return true;
  });

  const selected = docs.find((d) => d.id === selectedId) ?? null;

  return (
    <main className="page-fade max-w-8xl mx-auto px-6 py-6">
      {pollTimedOut && (
        <div
          className="mb-4 b-thin rounded-lg px-4 py-3 font-mono text-[11px] flex items-center gap-3"
          style={{ borderColor: '#a55a00', color: '#a55a00' }}
        >
          <span>L&apos;elaborazione sta richiedendo più tempo del previsto — controlla i log o riprova il documento.</span>
          <button
            className="ml-auto underline opacity-80 hover:opacity-100"
            onClick={() => { setPollTimedOut(false); refreshDocuments(); }}
          >
            Riprendi polling
          </button>
        </div>
      )}
      {/* Course header */}
      <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 px-6 py-5 mb-5 flex items-start gap-6">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 font-mono text-[11px] tracking-[0.12em] uppercase opacity-70 mb-3">
            <span>Academy</span>
            <span className="opacity-40">/</span>
            <span>Courses</span>
            <span className="opacity-40">/</span>
            <span className="font-semibold opacity-100 truncate">{course.title}</span>
          </div>
          <h1 className="text-3xl font-medium leading-tight">{course.title}</h1>
          {course.description && (
            <p className="font-mono text-[11px] opacity-70 mt-1">{course.description}</p>
          )}
        </div>

        <div className="flex items-center gap-6 b-thin-l pl-6">
          <Stat2 n={docs.length} k="documents" />
          <Stat2 n={indexed} k="indexed" />
          <Stat2 n={processing} k="processing" warn={processing > 0} />
          <Stat2 n={failed} k="failed" err={failed > 0} />
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            className="btn-ghost"
            onClick={() =>
              selected && router.push(`/courses/${courseId}/documents/${selected.id}/preview`)
            }
            disabled={!selected}
          >
            Open viewer
          </button>
          <button
            className="btn-ghost"
            onClick={handleReindexAll}
            disabled={reindexing || docs.length === 0}
            title="Re-ingest all documents (full parse → chunk → BM25 → QVAC)"
          >
            {reindexing ? 'Queuing…' : '↺ Reindex all'}
          </button>
          <button
            className="btn-ghost"
            onClick={() => setShowEdit(true)}
            title="Edit course title and description"
          >
            Edit
          </button>
          <button
            className="btn-ghost"
            onClick={handleDelete}
            disabled={deleting}
            style={{ color: '#b3261e' }}
            title="Delete course and all its documents"
          >
            {deleting ? 'Deleting…' : 'Delete'}
          </button>
          <button className="btn-primary" onClick={() => router.push(`/courses/${courseId}/study`)}>
            Study →
          </button>
        </div>
      </div>

      {/* Two columns */}
      <div className="grid grid-cols-12 gap-5">
        {/* LEFT — upload + document list */}
        <div className="col-span-12 lg:col-span-7 space-y-5">
          {/* Upload zone */}
          <div className="b-hard rounded-lg p-5 bg-white dark:bg-blue-dark/30">
            <div className="flex items-end justify-between b-thin-b pb-1.5 mb-3">
              <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">
                Upload · drop or click
              </span>
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-60">
                PDF · PPTX · MD · TXT · ≤ 50 MB
              </span>
            </div>
            <ErrorBoundary>
              <DocumentUpload
                courseId={courseId}
                accessToken={accessToken}
                onUploadComplete={refreshDocuments}
              />
            </ErrorBoundary>
          </div>

          {/* Filter bar */}
          <div className="flex items-center gap-2">
            {FILTER_OPTIONS.map((f) => (
              <button
                key={f.id}
                onClick={() => setFilter(f.id)}
                className={`font-mono text-[11px] tracking-[0.18em] uppercase px-3 h-8 rounded-md transition-all ${
                  filter === f.id
                    ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                    : 'b-thin hover:bg-blue-dark/5'
                }`}
              >
                {f.label}
              </button>
            ))}
            <span className="ml-auto font-mono text-[11px] opacity-60">
              {filtered.length} shown
            </span>
          </div>

          {/* Document list */}
          <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 overflow-hidden">
            <div className="grid grid-cols-[1fr_56px] sm:grid-cols-[1fr_100px_120px_56px] gap-3 px-4 py-2.5 b-thin-b font-mono text-[10px] tracking-[0.18em] uppercase opacity-70">
              <div>Document</div>
              <div className="hidden sm:block">Size</div>
              <div className="hidden sm:block">Status</div>
              <div />
            </div>

            {docsLoading ? (
              <div className="p-6 space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="animate-pulse h-12 bg-blue-dark/5 rounded" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              filter === 'all' ? (
                <div className="p-10 text-center">
                  <div className="mx-auto w-10 h-10 b-thin rounded-md mb-4 stripes" />
                  <p className="font-medium mb-1">Nessun documento ancora</p>
                  <p className="font-mono text-[11px] opacity-60 leading-relaxed mb-4 max-w-xs mx-auto">
                    Trascina un file PDF, PPTX, MD o TXT nell&apos;area sopra — o clicca per selezionarlo.
                    Academy lo indicizza e lo rende interrogabile dall&apos;AI tutor.
                  </p>
                </div>
              ) : (
                <div className="p-10 text-center font-mono text-[11px] opacity-60">
                  Nessun documento in questa vista.
                </div>
              )
            ) : (
              filtered.map((doc) => (
                <DocRow
                  key={doc.id}
                  doc={doc}
                  selected={doc.id === selectedId}
                  onSelect={() => setSelectedId(doc.id)}
                  onOpen={() => router.push(`/courses/${courseId}/documents/${doc.id}/preview`)}
                  onDeleted={refreshDocuments}
                  accessToken={accessToken}
                />
              ))
            )}
          </div>
        </div>

        {/* RIGHT — document detail panel */}
        <div className="col-span-12 lg:col-span-5">
          <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 sticky top-20">
            {selected ? (
              <>
                <div className="px-5 py-4 b-thin-b">
                  <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-1">
                    Document detail
                  </div>
                  <h3 className="font-medium leading-tight truncate">{selected.filename}</h3>
                  <div className="font-mono text-[11px] opacity-70 mt-1">
                    {selected.documentType || 'lecture'} · {formatSize(selected.size)}
                  </div>
                </div>
                <div className="p-5 space-y-5">
                  <div>
                    <div className="flex items-end justify-between b-thin-b pb-1.5 mb-3">
                      <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">
                        Lifecycle
                      </span>
                    </div>
                    <Lifecycle
                      status={selected.status}
                      processingStage={selected.processingStage}
                      updatedAt={selected.updatedAt}
                    />
                  </div>

                  {selected.status === 'error' && selected.errorMessage && (
                    <div
                      className="b-hard-1 rounded-md p-3"
                      style={{ borderColor: '#b3261e', color: '#b3261e' }}
                    >
                      <div className="font-mono text-[10px] tracking-[0.2em] uppercase mb-1">
                        Error
                      </div>
                      <div className="font-mono text-[12px] leading-relaxed">
                        {selected.errorMessage}
                      </div>
                    </div>
                  )}

                  <ErrorBoundary>
                    <DocumentProcessingPanel
                      documentId={selected.id}
                      accessToken={accessToken}
                      onViewPreview={() =>
                        router.push(`/courses/${courseId}/documents/${selected.id}/preview`)
                      }
                    />
                  </ErrorBoundary>

                  <div className="flex items-center gap-2 b-thin-t pt-4">
                    <button
                      className="btn-ghost"
                      onClick={() =>
                        router.push(`/courses/${courseId}/documents/${selected.id}/preview`)
                      }
                    >
                      Open in viewer →
                    </button>
                    <button
                      className="btn-primary"
                      onClick={() => router.push(`/courses/${courseId}/study`)}
                    >
                      Use in study
                    </button>
                    <span className="ml-auto font-mono text-[10px] opacity-60 truncate">
                      id · {selected.id.slice(0, 8)}
                    </span>
                  </div>
                </div>
              </>
            ) : (
              <div className="p-10 text-center">
                <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-1">
                  Document detail
                </div>
                <div className="font-mono text-[11px] opacity-50 mt-3">
                  Select a document to inspect it.
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {showEdit && course && (
        <EditCourseModal
          course={course}
          onClose={() => setShowEdit(false)}
          onSave={handleEdit}
        />
      )}
    </main>
  );
}

function Stat2({ n, k, warn, err }: { n: number; k: string; warn?: boolean; err?: boolean }) {
  const cls = err ? 'text-err' : warn ? 'text-warn' : '';
  return (
    <div className="text-center">
      <div className={`text-xl tnum font-medium ${cls}`}>{n}</div>
      <div className="font-mono text-[9px] tracking-[0.18em] uppercase opacity-70">{k}</div>
    </div>
  );
}

function DocRow({
  doc,
  selected,
  onSelect,
  onOpen,
  onDeleted,
  accessToken,
}: {
  doc: DocumentListRow;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
  onDeleted?: () => void;
  accessToken?: string;
}) {
  const { showToast } = useToast();
  const [deleting, setDeleting] = useState(false);
  const dot = STATE_DOT[doc.status] || '#7a7f9a';
  const animated = doc.status === 'processing' || doc.status === 'uploading';

  async function handleDelete(e: React.MouseEvent) {
    e.stopPropagation();
    if (!confirm(`Delete "${doc.filename}"?`)) return;
    setDeleting(true);
    try {
      await deleteDocument(doc.id, accessToken);
      onDeleted?.();
    } catch {
      showToast('Could not delete document. Try again.', 'err');
      setDeleting(false);
    }
  }

  return (
    <div
      onClick={onSelect}
      className={`grid grid-cols-[1fr_56px] sm:grid-cols-[1fr_100px_120px_56px] gap-3 px-4 py-3 b-thin-b items-center cursor-pointer transition-colors group ${
        selected ? 'bg-blue-dark/8 dark:bg-white/10' : 'hover:bg-blue-dark/5 dark:hover:bg-white/5'
      }`}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-10 b-thin stripes flex-shrink-0 rounded-sm" />
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{doc.filename}</div>
          <div className="font-mono text-[10px] opacity-60 mt-0.5 uppercase">
            {doc.documentType || 'lecture'}
          </div>
        </div>
      </div>

      <div className="hidden sm:block font-mono text-[11px] opacity-80 tnum">{formatSize(doc.size)}</div>

      <div className="hidden sm:block">
        <span className="chip" style={{ color: dot, borderColor: dot, border: '1px solid' }}>
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full ${animated ? 'dotpulse' : ''}`}
            style={{ background: dot }}
          />
          {doc.status}
        </span>
      </div>

      <div className="flex items-center gap-1">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onOpen();
          }}
          className="font-mono text-sm opacity-60 hover:opacity-100"
          title="Open preview"
        >
          →
        </button>
        <button
          onClick={handleDelete}
          disabled={deleting}
          className="opacity-0 group-hover:opacity-60 hover:!opacity-100 transition-opacity p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 disabled:cursor-not-allowed"
          title="Delete document"
        >
          {deleting ? (
            <svg className="h-3.5 w-3.5 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
            </svg>
          ) : (
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
            </svg>
          )}
        </button>
      </div>
    </div>
  );
}
