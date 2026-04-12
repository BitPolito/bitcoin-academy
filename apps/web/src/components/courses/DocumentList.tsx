'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { getDocumentListRows } from '@/lib/api/documents';
import type { DocumentListRow } from '@/lib/api/types';
import { ProcessingIndicator } from './ProcessingIndicator';
import { DocumentProcessingPanel } from '@/components/documents/DocumentProcessingPanel';

interface DocumentListProps {
  courseId: string;
  accessToken?: string;
  refreshKey?: number;
  onViewPreview?: (documentId: string) => void;
}

const AUTO_POLL_INTERVAL_MS = 8000;

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function DocumentList({
  courseId,
  accessToken,
  refreshKey = 0,
  onViewPreview,
}: DocumentListProps) {
  const [documents, setDocuments] = useState<DocumentListRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchDocuments = useCallback(
    async (silent = false) => {
      try {
        if (!silent) setError(null);
        const rows = await getDocumentListRows(courseId, accessToken);
        setDocuments(rows);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Failed to load documents';
        if (message.includes('Request failed (404)') || message.includes('Request failed (50')) {
          setDocuments([]);
          setError(null);
        } else if (!silent) {
          setError(message);
        }
      } finally {
        setLoading(false);
        setRefreshing(false);
      }
    },
    [courseId, accessToken],
  );

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments, refreshKey]);

  useEffect(() => {
    const hasInProgress = documents.some((d) => !d.isTerminal);
    if (hasInProgress) {
      pollRef.current = setInterval(() => fetchDocuments(true), AUTO_POLL_INTERVAL_MS);
    }
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [documents, fetchDocuments]);

  function handleRefresh() {
    setRefreshing(true);
    fetchDocuments();
  }

  function toggleExpand(id: string) {
    setExpandedId((prev) => (prev === id ? null : id));
  }

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
          onClick={() => fetchDocuments()}
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
        <svg
          className="mx-auto h-10 w-10 text-gray-300"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m6.75 12H9.75m3 0h.008v.008H12.75v-.008zM12 18.75h.008v.008H12v-.008zm-3 0h.008v.008H9v-.008zm6-6h.008v.008h-.008v-.008zm-3 0h.008v.008H12v-.008zm-3 0h.008v.008H9v-.008z"
          />
        </svg>
        <p className="mt-2 text-sm text-gray-500">No documents uploaded yet</p>
        <p className="text-xs text-gray-400">Upload slides, notes, or reference material to get started</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs text-gray-500">
          {documents.length} document{documents.length !== 1 ? 's' : ''}
        </p>
        <button
          onClick={handleRefresh}
          disabled={refreshing}
          className="inline-flex items-center gap-1 text-xs text-gray-500 hover:text-gray-700 disabled:opacity-50"
          title="Refresh list"
        >
          <svg
            className={`h-3.5 w-3.5 ${refreshing ? 'animate-spin' : ''}`}
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182"
            />
          </svg>
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
      </div>

      <ul className="divide-y divide-gray-100">
        {documents.map((doc) => {
          const isExpanded = expandedId === doc.id;
          return (
            <li key={doc.id} className="py-2 px-1">
              <button
                type="button"
                onClick={() => toggleExpand(doc.id)}
                className="w-full text-left rounded-md hover:bg-gray-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-orange-400"
                aria-expanded={isExpanded}
              >
                <div className="flex items-start gap-3">
                  {/* Expand chevron */}
                  <svg
                    className={`mt-1 h-4 w-4 flex-shrink-0 text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                    fill="none"
                    viewBox="0 0 24 24"
                    strokeWidth={2}
                    stroke="currentColor"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
                  </svg>

                  {/* File type badge */}
                  <span className="flex-shrink-0 mt-0.5 inline-flex items-center justify-center h-8 w-8 rounded-md bg-gray-100 text-[10px] font-bold text-gray-500 uppercase">
                    {doc.fileType}
                  </span>

                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-gray-900 truncate">{doc.filename}</p>
                      <ProcessingIndicator status={doc.status} stage={doc.processingStage} />
                    </div>

                    <div className="mt-0.5 flex items-center gap-3 text-xs text-gray-500">
                      <span>{formatFileSize(doc.size)}</span>
                      <span title="Uploaded">{formatTime(doc.createdAt)}</span>
                      <span title="Last updated">updated {formatTime(doc.updatedAt)}</span>
                    </div>

                    {doc.status === 'error' && doc.errorMessage && (
                      <p className="mt-1 text-xs text-red-600 truncate" title={doc.errorMessage}>
                        {doc.errorMessage}
                      </p>
                    )}
                  </div>
                </div>
              </button>

              {/* Expandable detail panel (U-05) */}
              {isExpanded && (
                <div className="mt-2 ml-7">
                  <DocumentProcessingPanel
                    documentId={doc.id}
                    accessToken={accessToken}
                    onViewPreview={onViewPreview}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
