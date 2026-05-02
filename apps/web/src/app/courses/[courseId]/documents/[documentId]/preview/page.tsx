'use client';

import { Suspense, useCallback, useEffect, useRef, useState } from 'react';
import { useParams, useRouter, useSearchParams } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { getDocumentPreviewView } from '@/lib/api/documents';
import type { DocumentPreviewView, ApiPreviewChunk } from '@/lib/api/types';

// ── Helpers ───────────────────────────────────────────────────────────────────

function uniqueSections(chunks: ApiPreviewChunk[]): { name: string; firstIndex: number }[] {
  const seen = new Map<string, number>();
  chunks.forEach((c, i) => {
    const key = c.section ?? '';
    if (!seen.has(key)) seen.set(key, i);
  });
  return Array.from(seen.entries()).map(([name, firstIndex]) => ({ name, firstIndex }));
}

// ── Spinner ───────────────────────────────────────────────────────────────────

function Spinner() {
  return (
    <div className="h-[calc(100vh-48px)] flex items-center justify-center">
      <div className="w-5 h-5 rounded-full border-2 border-blue-dark border-t-transparent animate-spin" />
    </div>
  );
}

// ── Outline pane (3 col) ──────────────────────────────────────────────────────

function OutlinePane({
  sections,
  activeChunkIndex,
  onSelect,
}: {
  sections: { name: string; firstIndex: number }[];
  activeChunkIndex: number;
  onSelect: (i: number) => void;
}) {
  const activeSection = [...sections].reverse().find(s => s.firstIndex <= activeChunkIndex);

  return (
    <div className="h-full flex flex-col b-thin-r">
      <div className="flex-shrink-0 px-4 py-3 b-thin-b">
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">Outline</span>
      </div>
      {sections.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="font-mono text-[11px] opacity-50 text-center px-4">No sections found</p>
        </div>
      ) : (
        <nav className="flex-1 overflow-y-auto ws-scroll p-2">
          <ul className="space-y-0.5">
            {sections.map((s, i) => {
              const isActive = activeSection?.name === s.name;
              return (
                <li key={i}>
                  <button
                    onClick={() => onSelect(s.firstIndex)}
                    className={`w-full text-left px-3 py-2 rounded text-[11px] font-mono transition-colors truncate ${
                      isActive
                        ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                        : 'hover:bg-blue-dark/5 dark:hover:bg-white/10 opacity-80'
                    }`}
                  >
                    {s.name || `Section ${i + 1}`}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </div>
  );
}

// ── Center viewer (6 col) ─────────────────────────────────────────────────────

function ViewerPane({
  chunks,
  activeIndex,
  fallbackText,
}: {
  chunks: ApiPreviewChunk[];
  activeIndex: number;
  fallbackText: string | null;
}) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const activeRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeIndex]);

  if (chunks.length === 0) {
    return (
      <div className="h-full overflow-y-auto ws-scroll p-6">
        {fallbackText ? (
          <pre className="font-mono text-[12.5px] leading-relaxed whitespace-pre-wrap opacity-90">
            {fallbackText}
          </pre>
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <div className="mx-auto w-10 h-10 b-thin rounded-md mb-4 stripes" />
              <p className="font-mono text-[11px] opacity-60">No content available yet.</p>
            </div>
          </div>
        )}
      </div>
    );
  }

  return (
    <div ref={containerRef} className="h-full overflow-y-auto ws-scroll px-6 py-4 space-y-3">
      {chunks.map((chunk, i) => {
        const isActive = activeIndex === i;
        return (
          <div
            key={i}
            ref={isActive ? (el) => { activeRef.current = el; } : undefined}
            className={`rounded-lg px-4 py-3 transition-all ${
              isActive
                ? 'bg-blue-dark/10 b-thin ring-1 ring-blue-dark/40 dark:ring-white/30'
                : 'b-thin'
            }`}
          >
            <div className="flex items-center gap-3 mb-2">
              <span
                className={`font-mono text-[10px] tracking-[0.18em] uppercase ${
                  isActive ? 'text-blue-dark dark:text-white font-semibold' : 'opacity-50'
                }`}
              >
                {chunk.label ?? `Chunk ${i + 1}`}
              </span>
              {chunk.section && (
                <span className="font-mono text-[10px] opacity-40 truncate">· {chunk.section}</span>
              )}
            </div>
            <p className="text-[13.5px] leading-relaxed whitespace-pre-wrap opacity-90">
              {chunk.text}
            </p>
          </div>
        );
      })}
    </div>
  );
}

// ── Chunk browser (3 col) ─────────────────────────────────────────────────────

function ChunkBrowser({
  chunks,
  activeIndex,
  onSelect,
}: {
  chunks: ApiPreviewChunk[];
  activeIndex: number;
  onSelect: (i: number) => void;
}) {
  return (
    <div className="h-full flex flex-col b-thin-l">
      <div className="flex-shrink-0 px-4 py-3 b-thin-b flex items-center justify-between">
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">Chunks</span>
        <span className="font-mono text-[10px] opacity-50">{chunks.length}</span>
      </div>
      {chunks.length === 0 ? (
        <div className="flex-1 flex items-center justify-center">
          <p className="font-mono text-[11px] opacity-50 text-center px-4">No chunks indexed</p>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto ws-scroll p-2 space-y-1">
          {chunks.map((chunk, i) => {
            const isActive = activeIndex === i;
            return (
              <button
                key={i}
                onClick={() => onSelect(i)}
                className={`w-full text-left rounded-md px-3 py-2 transition-colors ${
                  isActive
                    ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                    : 'b-thin hover:bg-blue-dark/5 dark:hover:bg-white/10'
                }`}
              >
                <div className={`font-mono text-[10px] mb-0.5 truncate ${isActive ? 'opacity-80' : 'opacity-60'}`}>
                  {chunk.label ?? `Chunk ${i + 1}`}
                </div>
                <p className={`text-[11px] line-clamp-2 ${isActive ? 'opacity-90' : 'opacity-70'}`}>
                  {chunk.text.slice(0, 90)}
                </p>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main content (needs useSearchParams → Suspense) ───────────────────────────

function PreviewContent() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session } = useSession();

  const courseId = params.courseId as string;
  const documentId = params.documentId as string;
  const accessToken = (session?.user as any)?.accessToken;

  const pageParam = Math.max(1, parseInt(searchParams.get('page') ?? '1', 10));

  const [preview, setPreview] = useState<DocumentPreviewView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState(pageParam - 1);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      setError(null);
      setLoading(true);
      const data = await getDocumentPreviewView(documentId, accessToken);
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load preview');
    } finally {
      setLoading(false);
    }
  }, [documentId, accessToken]);

  useEffect(() => { load(); }, [load]);

  // Sync ?page= to activeIndex once chunks are loaded
  useEffect(() => {
    if (preview?.sampleChunks) {
      const clamped = Math.min(pageParam - 1, preview.sampleChunks.length - 1);
      setActiveIndex(Math.max(0, clamped));
    }
  }, [preview, pageParam]);

  if (loading) return <Spinner />;

  if (error || !preview) {
    return (
      <div className="h-[calc(100vh-48px)] flex items-center justify-center p-8">
        <div className="b-thin rounded-lg p-6 text-center max-w-sm w-full">
          <p className="font-mono text-[11px] opacity-70 mb-4">{error ?? 'Preview not available'}</p>
          <div className="flex items-center justify-center gap-4">
            <button onClick={load} className="btn-ghost text-sm">Retry</button>
            <button
              onClick={() => router.push(`/courses/${courseId}`)}
              className="font-mono text-[11px] opacity-60 hover:opacity-100 transition-opacity"
            >
              ← Back
            </button>
          </div>
        </div>
      </div>
    );
  }

  const chunks = preview.sampleChunks ?? [];
  const sections = uniqueSections(chunks);

  return (
    <div className="h-[calc(100vh-48px)] flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 b-thin-b px-5 py-3 flex items-center gap-4 bg-white dark:bg-blue-dark/30">
        <button
          onClick={() => router.push(`/courses/${courseId}`)}
          className="flex items-center gap-1.5 font-mono text-[11px] opacity-60 hover:opacity-100 transition-opacity flex-shrink-0"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          Back
        </button>

        <div className="flex-1 min-w-0">
          <span className="font-medium text-sm truncate">{preview.filename}</span>
          {(preview.pageCount != null || chunks.length > 0) && (
            <span className="ml-3 font-mono text-[10px] opacity-50">
              {preview.pageCount != null ? `${preview.pageCount} pages` : ''}
              {preview.pageCount != null && chunks.length > 0 ? ' · ' : ''}
              {chunks.length > 0 ? `${chunks.length} chunks` : ''}
            </span>
          )}
        </div>

        {chunks.length > 0 && (
          <div className="flex items-center gap-1 font-mono text-[11px] opacity-60 flex-shrink-0">
            <button
              onClick={() => setActiveIndex(i => Math.max(0, i - 1))}
              disabled={activeIndex === 0}
              className="px-2 py-1 rounded b-thin disabled:opacity-30 hover:bg-blue-dark/5 transition-colors"
              aria-label="Previous chunk"
            >
              ‹
            </button>
            <span className="px-2 tabular-nums">{activeIndex + 1} / {chunks.length}</span>
            <button
              onClick={() => setActiveIndex(i => Math.min(chunks.length - 1, i + 1))}
              disabled={activeIndex === chunks.length - 1}
              className="px-2 py-1 rounded b-thin disabled:opacity-30 hover:bg-blue-dark/5 transition-colors"
              aria-label="Next chunk"
            >
              ›
            </button>
          </div>
        )}
      </div>

      {/* 3-pane body */}
      <div className="flex-1 min-h-0 grid grid-cols-12 bg-white dark:bg-blue-dark/20">
        <div className="col-span-3">
          <OutlinePane
            sections={sections}
            activeChunkIndex={activeIndex}
            onSelect={setActiveIndex}
          />
        </div>
        <div className="col-span-6">
          <ViewerPane
            chunks={chunks}
            activeIndex={activeIndex}
            fallbackText={preview.extractedTextPreview}
          />
        </div>
        <div className="col-span-3">
          <ChunkBrowser
            chunks={chunks}
            activeIndex={activeIndex}
            onSelect={setActiveIndex}
          />
        </div>
      </div>
    </div>
  );
}

// ── Page export ───────────────────────────────────────────────────────────────

export default function DocumentPreviewPage() {
  return (
    <Suspense fallback={<Spinner />}>
      <PreviewContent />
    </Suspense>
  );
}
