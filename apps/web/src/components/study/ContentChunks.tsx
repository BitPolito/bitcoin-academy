'use client';

import { useEffect, useState } from 'react';
import { getDocuments } from '@/lib/services/documents';
import { getDocumentPreviewView } from '@/lib/api/documents';

// Typed shapes for document preview data returned by the backend
interface Section {
  title?: string;
  level?: number;
  page?: number;
}

interface Chunk {
  text: string;
  section?: string;
  page?: number;
}

interface DocumentContent {
  documentId: string;
  filename: string;
  sections: Section[];
  chunks: Chunk[];
}

interface ContentChunksProps {
  courseId: string;
  accessToken?: string;
  className?: string;
  activeCitationDocIds?: Set<string>;
}

export function ContentChunks({ courseId, accessToken, className, activeCitationDocIds }: ContentChunksProps) {
  const [contents, setContents] = useState<DocumentContent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchContent() {
      try {
        const docs = await getDocuments(courseId, accessToken);
        const readyDocs = docs.filter((d) => d.status === 'ready');

        const previews = await Promise.allSettled(
          readyDocs.map(async (doc) => {
            const preview = await getDocumentPreviewView(doc.id, accessToken);
            return {
              documentId: doc.id,
              filename: doc.filename,
              sections: (preview.sections ?? []).map((title) => ({ title })),
              chunks: (preview.sampleChunks ?? []).map((c) => ({
                text: c.text,
                section: c.section ?? undefined,
              })),
            };
          })
        );

        const loaded = previews
          .flatMap((r) => (r.status === 'fulfilled' ? [r.value] : []))
          .filter((d) => d.chunks.length > 0 || d.sections.length > 0);

        setContents(loaded);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load course material');
      } finally {
        setLoading(false);
      }
    }

    fetchContent();
  }, [courseId, accessToken]);

  if (loading) {
    return (
      <div className={className} aria-label="Loading course material">
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse">
              <div className="h-3 w-1/3 bg-gray-200 rounded mb-2" />
              <div className="h-3 w-full bg-gray-100 rounded mb-1" />
              <div className="h-3 w-4/5 bg-gray-100 rounded" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className={className}>
        <p className="text-xs text-red-500">{error}</p>
      </div>
    );
  }

  if (contents.length === 0) {
    return null;
  }

  return (
    <div className={className}>
      <div className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70 mb-3">
        Course Material
      </div>
      <div className="space-y-5">
        {contents.map((doc) => {
          const isCited = activeCitationDocIds?.has(doc.documentId);
          return (
          <div
            key={doc.documentId}
            className={`rounded-md transition-colors ${isCited ? 'b-hard bg-blue-dark/5 dark:bg-blue-dark/20 p-2' : ''}`}
          >
            <div className="flex items-center gap-2 mb-2">
              {isCited && (
                <span className="inline-block w-1.5 h-1.5 rounded-full bg-blue-dark dark:bg-white flex-shrink-0" />
              )}
              <p className="font-mono text-[10px] tracking-wide truncate opacity-80" title={doc.filename}>
                {doc.filename}
              </p>
            </div>

            {/* Section chips */}
            {doc.sections.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-2">
                {doc.sections.map((section, i) => (
                  <span key={i} className="chip" style={{ border: '1px solid currentColor' }}>
                    {section.title ?? `Section ${i + 1}`}
                  </span>
                ))}
              </div>
            )}

            {/* Sample chunks */}
            <div className="space-y-1.5">
              {doc.chunks.map((chunk, i) => (
                <div key={i} className="b-thin rounded-md p-2.5 text-[12px] leading-relaxed">
                  <div className="flex items-start gap-2">
                    <span className="flex-shrink-0 font-mono text-[10px] opacity-50 mt-0.5">{i + 1}</span>
                    <p className="flex-1 opacity-90">{chunk.text}</p>
                  </div>
                  {chunk.section && (
                    <p className="mt-1 font-mono text-[10px] opacity-50 pl-5">§ {chunk.section}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
}
