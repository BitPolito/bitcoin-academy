'use client';

import { useEffect, useState, useCallback } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { getCourse, type Course } from '@/lib/services/courses';
import { DocumentUpload } from '@/components/documents/DocumentUpload';
import { ErrorBoundary } from '@/components/ui/ErrorBoundary';
import { getDocumentListRows } from '@/lib/api/documents';
import type { DocumentListRow, MaterialType } from '@/lib/api/types';
import { DocumentProcessingPanel } from '@/components/documents/DocumentProcessingPanel';

type DocFilter = 'all' | 'ready' | 'processing' | 'error';

const FILTER_OPTIONS: { id: DocFilter; label: string }[] = [
  { id: 'all',        label: 'All' },
  { id: 'ready',      label: 'Indexed' },
  { id: 'processing', label: 'Processing' },
  { id: 'error',      label: 'Failed' },
];

function formatSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const STATE_DOT: Record<string, string> = {
  ready:      '#1a7f3a',
  processing: '#a55a00',
  uploading:  '#a55a00',
  error:      '#b3261e',
};

const LIFECYCLE_STAGES = ['uploading', 'processing', 'ready'] as const;

function Lifecycle({ status }: { status: string }) {
  const failed = status === 'error';
  const idx = failed ? -1 : LIFECYCLE_STAGES.indexOf(status as any);
  return (
    <div className="flex items-center gap-1.5">
      {LIFECYCLE_STAGES.map((s, i) => {
        const done = !failed && i < idx;
        const here = !failed && i === idx;
        return (
          <div key={s} className="flex items-center gap-1.5 flex-1">
            <div
              className={`flex-1 h-7 b-thin rounded-sm flex items-center justify-center font-mono text-[10px] tracking-[0.16em] uppercase ${
                done ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                     : here ? 'bg-blue-dark/10'
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
        <span className="ml-2 chip" style={{ color: '#b3261e', border: '1px solid #b3261e' }}>FAILED</span>
      )}
    </div>
  );
}

export default function CourseWorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.courseId as string;
  const { data: session } = useSession();
  const accessToken = (session?.user as any)?.accessToken;

  const [course, setCourse] = useState<Course | null>(null);
  const [docs, setDocs] = useState<DocumentListRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [docsLoading, setDocsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [filter, setFilter] = useState<DocFilter>('all');
  const [refreshKey, setRefreshKey] = useState(0);

  const refreshDocuments = useCallback(() => setRefreshKey((k) => k + 1), []);

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
        <div className="b-hard rounded-lg p-6 text-center" style={{ borderColor: '#b3261e', color: '#b3261e' }}>
          <p className="text-sm">{error || 'Course not found'}</p>
          <button onClick={() => window.location.reload()} className="mt-3 text-sm font-medium underline">Retry</button>
        </div>
      </main>
    );
  }

  const indexed    = docs.filter((d) => d.status === 'ready').length;
  const processing = docs.filter((d) => d.status === 'processing' || d.status === 'uploading').length;
  const failed     = docs.filter((d) => d.status === 'error').length;

  const filtered = docs.filter((d) => {
    if (filter === 'all')        return true;
    if (filter === 'ready')      return d.status === 'ready';
    if (filter === 'processing') return d.status === 'processing' || d.status === 'uploading';
    if (filter === 'error')      return d.status === 'error';
    return true;
  });

  const selected = docs.find((d) => d.id === selectedId) ?? null;

  return (
    <main className="page-fade max-w-8xl mx-auto px-6 py-6">
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
          <Stat2 n={docs.length}  k="documents" />
          <Stat2 n={indexed}      k="indexed" />
          <Stat2 n={processing}   k="processing" warn={processing > 0} />
          <Stat2 n={failed}       k="failed"     err={failed > 0} />
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            className="btn-ghost"
            onClick={() => selected && router.push(`/courses/${courseId}/documents/${selected.id}/preview`)}
            disabled={!selected}
          >
            Open viewer
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
              <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">Upload · drop or click</span>
              <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-60">PDF · PPTX · MD · TXT · ≤ 50 MB</span>
            </div>
            <ErrorBoundary>
              <DocumentUpload courseId={courseId} accessToken={accessToken} onUploadComplete={refreshDocuments} />
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
            <span className="ml-auto font-mono text-[11px] opacity-60">{filtered.length} shown</span>
          </div>

          {/* Document list */}
          <div className="b-hard rounded-lg bg-white dark:bg-blue-dark/30 overflow-hidden">
            <div className="grid grid-cols-[1fr_100px_120px_30px] gap-3 px-4 py-2.5 b-thin-b font-mono text-[10px] tracking-[0.18em] uppercase opacity-70">
              <div>Document</div>
              <div>Size</div>
              <div>Status</div>
              <div />
            </div>

            {docsLoading ? (
              <div className="p-6 space-y-3">
                {[1, 2, 3].map((i) => (
                  <div key={i} className="animate-pulse h-12 bg-blue-dark/5 rounded" />
                ))}
              </div>
            ) : filtered.length === 0 ? (
              <div className="p-10 text-center font-mono text-[11px] opacity-60">
                {filter === 'all' ? 'No documents uploaded yet.' : 'No documents in this view.'}
              </div>
            ) : (
              filtered.map((doc) => (
                <DocRow
                  key={doc.id}
                  doc={doc}
                  selected={doc.id === selectedId}
                  onSelect={() => setSelectedId(doc.id)}
                  onOpen={() => router.push(`/courses/${courseId}/documents/${doc.id}/preview`)}
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
                  <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-1">Document detail</div>
                  <h3 className="font-medium leading-tight truncate">{selected.filename}</h3>
                  <div className="font-mono text-[11px] opacity-70 mt-1">
                    {(selected as any).documentType || 'lecture'} · {formatSize(selected.size)}
                  </div>
                </div>
                <div className="p-5 space-y-5">
                  <div>
                    <div className="flex items-end justify-between b-thin-b pb-1.5 mb-3">
                      <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">Lifecycle</span>
                    </div>
                    <Lifecycle status={selected.status} />
                    {selected.processingStage && (
                      <div className="font-mono text-[11px] opacity-70 mt-2">stage · {selected.processingStage}</div>
                    )}
                  </div>

                  {selected.status === 'error' && selected.errorMessage && (
                    <div className="b-hard-1 rounded-md p-3" style={{ borderColor: '#b3261e', color: '#b3261e' }}>
                      <div className="font-mono text-[10px] tracking-[0.2em] uppercase mb-1">Error</div>
                      <div className="font-mono text-[12px] leading-relaxed">{selected.errorMessage}</div>
                    </div>
                  )}

                  <ErrorBoundary>
                    <DocumentProcessingPanel
                      documentId={selected.id}
                      accessToken={accessToken}
                      onViewPreview={() => router.push(`/courses/${courseId}/documents/${selected.id}/preview`)}
                    />
                  </ErrorBoundary>

                  <div className="flex items-center gap-2 b-thin-t pt-4">
                    <button
                      className="btn-ghost"
                      onClick={() => router.push(`/courses/${courseId}/documents/${selected.id}/preview`)}
                    >
                      Open in viewer →
                    </button>
                    <button className="btn-primary" onClick={() => router.push(`/courses/${courseId}/study`)}>
                      Use in study
                    </button>
                    <span className="ml-auto font-mono text-[10px] opacity-60 truncate">id · {selected.id.slice(0, 8)}</span>
                  </div>
                </div>
              </>
            ) : (
              <div className="p-10 text-center">
                <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-1">Document detail</div>
                <div className="font-mono text-[11px] opacity-50 mt-3">Select a document to inspect it.</div>
              </div>
            )}
          </div>
        </div>
      </div>
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
}: {
  doc: DocumentListRow;
  selected: boolean;
  onSelect: () => void;
  onOpen: () => void;
}) {
  const dot = STATE_DOT[doc.status] || '#7a7f9a';
  const animated = doc.status === 'processing' || doc.status === 'uploading';

  return (
    <div
      onClick={onSelect}
      className={`grid grid-cols-[1fr_100px_120px_30px] gap-3 px-4 py-3 b-thin-b items-center cursor-pointer transition-colors ${
        selected ? 'bg-blue-dark/8 dark:bg-white/10' : 'hover:bg-blue-dark/5 dark:hover:bg-white/5'
      }`}
    >
      <div className="flex items-center gap-3 min-w-0">
        <div className="w-8 h-10 b-thin stripes flex-shrink-0 rounded-sm" />
        <div className="min-w-0">
          <div className="text-sm font-medium truncate">{doc.filename}</div>
          <div className="font-mono text-[10px] opacity-60 mt-0.5 uppercase">
            {(doc as any).documentType || 'lecture'}
          </div>
        </div>
      </div>

      <div className="font-mono text-[11px] opacity-80 tnum">{formatSize(doc.size)}</div>

      <div>
        <span className="chip" style={{ color: dot, borderColor: dot, border: '1px solid' }}>
          <span
            className={`inline-block w-1.5 h-1.5 rounded-full ${animated ? 'dotpulse' : ''}`}
            style={{ background: dot }}
          />
          {doc.status}
        </span>
      </div>

      <button
        onClick={(e) => { e.stopPropagation(); onOpen(); }}
        className="font-mono text-sm opacity-60 hover:opacity-100"
      >
        →
      </button>
    </div>
  );
}
