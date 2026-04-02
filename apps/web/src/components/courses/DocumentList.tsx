'use client';

import { useEffect, useState, useCallback } from 'react';
import type { CourseDocument } from '@/lib/services/documents';
import { getDocuments } from '@/lib/services/documents';
import { ProcessingIndicator } from './ProcessingIndicator';

interface DocumentListProps {
  courseId: string;
  accessToken?: string;
  refreshKey?: number;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function DocumentList({ courseId, accessToken, refreshKey = 0 }: DocumentListProps) {
  const [documents, setDocuments] = useState<CourseDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDocuments = useCallback(async () => {
    try {
      setError(null);
      const docs = await getDocuments(courseId, accessToken);
      setDocuments(docs);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load documents';
      if (message.includes('Request failed (404)') || message.includes('Request failed (50')) {
        setDocuments([]);
        setError(null);
      } else {
        setError(message);
      }
    } finally {
      setLoading(false);
    }
  }, [courseId, accessToken]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments, refreshKey]);

  if (loading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="animate-pulse flex items-center gap-3 p-3 rounded-lg bg-gray-50">
            <div className="h-8 w-8 rounded bg-gray-200" />
            <div className="flex-1 space-y-1.5">
              <div className="h-3 w-2/3 rounded bg-gray-200" />
              <div className="h-2.5 w-1/4 rounded bg-gray-200" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50 p-4">
        <p className="text-sm text-red-700">{error}</p>
        <button
          onClick={fetchDocuments}
          className="mt-2 text-sm font-medium text-red-700 hover:text-red-800 underline"
        >
          Retry
        </button>
      </div>
    );
  }

  if (documents.length === 0) {
    return (
      <div className="text-center py-8 px-4">
        <svg className="mx-auto h-10 w-10 text-gray-300" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12H9.75m3 0h.008v.008H12.75v-.008zM12 18.75h.008v.008H12v-.008zm-3 0h.008v.008H9v-.008zm6-6h.008v.008h-.008v-.008zm-3 0h.008v.008H12v-.008zm-3 0h.008v.008H9v-.008z" />
        </svg>
        <p className="mt-2 text-sm text-gray-500">No documents uploaded yet</p>
        <p className="text-xs text-gray-400">Upload slides, notes, or reference material to get started</p>
      </div>
    );
  }

  return (
    <ul className="divide-y divide-gray-100">
      {documents.map((doc) => (
        <li key={doc.id} className="flex items-center gap-3 py-3 px-1">
          <div className="flex-shrink-0">
            <svg className="h-7 w-7 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
            </svg>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-gray-900 truncate">{doc.filename}</p>
            <p className="text-xs text-gray-500">{formatFileSize(doc.size)}</p>
          </div>
          <ProcessingIndicator status={doc.status} />
        </li>
      ))}
    </ul>
  );
}
