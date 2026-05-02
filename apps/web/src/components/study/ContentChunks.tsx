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
}

export function ContentChunks({ courseId, accessToken, className }: ContentChunksProps) {
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
      <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-3">
        Course Material
      </h4>
      <div className="space-y-6">
        {contents.map((doc) => (
          <div key={doc.documentId}>
            <p
              className="text-xs font-medium text-gray-600 mb-2 truncate"
              title={doc.filename}
            >
              {doc.filename}
            </p>

            {/* Section chips — each named section from the parsed document */}
            {doc.sections.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-3">
                {doc.sections.map((section, i) => (
                  <span
                    key={i}
                    className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-orange-50 text-orange-700 border border-orange-200"
                  >
                    {section.title ?? `Section ${i + 1}`}
                  </span>
                ))}
              </div>
            )}

            {/* Sample chunks — numbered excerpts from the document */}
            <div className="space-y-2">
              {doc.chunks.map((chunk, i) => (
                <div
                  key={i}
                  className="rounded-md bg-white border border-gray-200 p-3 text-xs text-gray-700 leading-relaxed"
                >
                  <div className="flex items-start gap-2">
                    <span className="flex-shrink-0 inline-flex items-center justify-center h-4 w-4 rounded-full bg-gray-100 text-gray-500 text-[10px] font-semibold mt-0.5">
                      {i + 1}
                    </span>
                    <p className="flex-1">{chunk.text}</p>
                  </div>
                  {chunk.section && (
                    <p className="mt-1 text-[10px] text-gray-400 pl-6">§ {chunk.section}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
