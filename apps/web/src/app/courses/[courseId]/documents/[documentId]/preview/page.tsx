'use client';

import { useCallback, useEffect, useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useSession } from 'next-auth/react';
import { getDocumentPreviewView } from '@/lib/api/documents';
import type { DocumentPreviewView } from '@/lib/api/types';

export default function DocumentPreviewPage() {
  const params = useParams();
  const router = useRouter();
  const courseId = params.courseId as string;
  const documentId = params.documentId as string;
  const { data: session } = useSession();
  const accessToken = (session?.user as any)?.accessToken;

  const [preview, setPreview] = useState<DocumentPreviewView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await getDocumentPreviewView(documentId, accessToken);
      setPreview(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load preview');
    } finally {
      setLoading(false);
    }
  }, [documentId, accessToken]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-6 w-1/3 bg-gray-200 rounded" />
          <div className="h-64 bg-gray-100 rounded-lg" />
          <div className="h-40 bg-gray-100 rounded-lg" />
        </div>
      </main>
    );
  }

  if (error || !preview) {
    return (
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="rounded-lg border border-red-200 bg-red-50 p-6 text-center">
          <p className="text-sm text-red-700">{error || 'Preview not available'}</p>
          <div className="mt-3 flex items-center justify-center gap-3">
            <button
              onClick={load}
              className="text-sm font-medium text-red-700 hover:text-red-800 underline"
            >
              Retry
            </button>
            <button
              onClick={() => router.push(`/courses/${courseId}`)}
              className="text-sm font-medium text-gray-600 hover:text-gray-800 underline"
            >
              Back to course
            </button>
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-6 flex items-center gap-3">
        <button
          onClick={() => router.push(`/courses/${courseId}`)}
          className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700"
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          Back
        </button>
        <div className="flex-1 min-w-0">
          <h1 className="text-xl font-bold text-gray-900 truncate">{preview.filename}</h1>
          {preview.pageCount != null && (
            <p className="text-sm text-gray-500">{preview.pageCount} page{preview.pageCount !== 1 ? 's' : ''}</p>
          )}
        </div>
      </div>

      <div className="space-y-6">
        {/* Extracted text preview */}
        <section className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="text-base font-semibold text-gray-900">Extracted Text</h2>
          </div>
          <div className="p-6">
            {preview.extractedTextPreview ? (
              <pre className="text-sm text-gray-800 whitespace-pre-wrap font-mono bg-gray-50 rounded-md p-4 max-h-96 overflow-auto">
                {preview.extractedTextPreview}
              </pre>
            ) : (
              <p className="text-sm text-gray-400 italic">No extracted text available yet.</p>
            )}
          </div>
        </section>

        {/* Sections / page segmentation */}
        <section className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="text-base font-semibold text-gray-900">Sections / Page Segmentation</h2>
          </div>
          <div className="p-6">
            {preview.sections && preview.sections.length > 0 ? (
              <div className="space-y-3">
                {preview.sections.map((section, i) => (
                  <div key={i} className="rounded-md border border-gray-200 p-3">
                    <p className="text-xs font-medium text-gray-500 mb-1">Section {i + 1}</p>
                    <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono max-h-40 overflow-auto">
                      {JSON.stringify(section, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 italic">No sections data available yet.</p>
            )}
          </div>
        </section>

        {/* Sample chunks */}
        <section className="bg-white rounded-lg shadow">
          <div className="px-6 py-4 border-b border-gray-100">
            <h2 className="text-base font-semibold text-gray-900">Sample Chunks</h2>
          </div>
          <div className="p-6">
            {preview.sampleChunks && preview.sampleChunks.length > 0 ? (
              <div className="space-y-3">
                {preview.sampleChunks.map((chunk, i) => (
                  <div key={i} className="rounded-md border border-gray-200 p-3">
                    <p className="text-xs font-medium text-gray-500 mb-1">Chunk {i + 1}</p>
                    <pre className="text-xs text-gray-700 whitespace-pre-wrap font-mono max-h-40 overflow-auto">
                      {typeof chunk === 'string' ? chunk : JSON.stringify(chunk, null, 2)}
                    </pre>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-gray-400 italic">No chunk samples available yet.</p>
            )}
          </div>
        </section>
      </div>
    </main>
  );
}
