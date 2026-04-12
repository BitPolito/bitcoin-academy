'use client';

import { useCallback, useEffect, useState } from 'react';
import { getDocumentDetailView } from '@/lib/api/documents';
import type { DocumentDetailView } from '@/lib/api/types';

interface DocumentProcessingPanelProps {
  documentId: string;
  accessToken?: string;
  onViewPreview?: (documentId: string) => void;
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-start justify-between py-1.5">
      <dt className="text-xs font-medium text-gray-500 w-36 flex-shrink-0">{label}</dt>
      <dd className="text-xs text-gray-900 text-right">{value ?? <span className="text-gray-400">N/A</span>}</dd>
    </div>
  );
}

export function DocumentProcessingPanel({
  documentId,
  accessToken,
  onViewPreview,
}: DocumentProcessingPanelProps) {
  const [detail, setDetail] = useState<DocumentDetailView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setError(null);
      const data = await getDocumentDetailView(documentId, accessToken);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load document details');
    } finally {
      setLoading(false);
    }
  }, [documentId, accessToken]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return (
      <div className="animate-pulse space-y-2 py-3 px-4">
        <div className="h-3 w-2/3 rounded bg-gray-200" />
        <div className="h-3 w-1/2 rounded bg-gray-200" />
        <div className="h-3 w-3/4 rounded bg-gray-200" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="py-3 px-4">
        <p className="text-xs text-red-600">{error}</p>
        <button onClick={load} className="mt-1 text-xs text-red-700 hover:text-red-800 underline">
          Retry
        </button>
      </div>
    );
  }

  if (!detail) return null;

  return (
    <div className="py-3 px-4 bg-gray-50 rounded-md space-y-1">
      <dl className="divide-y divide-gray-100">
        <DetailRow label="Raw status" value={detail.status} />
        <DetailRow label="Processing stage" value={detail.processingStage} />
        <DetailRow label="Parser used" value={detail.parserUsed} />
        <DetailRow label="Page / slide count" value={detail.pageCount} />
        <DetailRow label="Chunk count" value={detail.chunkCount} />
        <DetailRow label="Indexing status" value={detail.indexingStatus} />
        {detail.errorMessage && (
          <DetailRow
            label="Processing errors"
            value={<span className="text-red-600">{detail.errorMessage}</span>}
          />
        )}
        {detail.normalizedMetadata && (
          <div className="py-1.5">
            <dt className="text-xs font-medium text-gray-500 mb-1">Normalized metadata</dt>
            <dd className="text-[11px] font-mono bg-white rounded border border-gray-200 p-2 max-h-32 overflow-auto whitespace-pre-wrap">
              {JSON.stringify(detail.normalizedMetadata, null, 2)}
            </dd>
          </div>
        )}
      </dl>

      {onViewPreview && detail.status === 'ready' && (
        <button
          onClick={() => onViewPreview(detail.id)}
          className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-orange-600 hover:text-orange-700"
        >
          View extracted content
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M13.5 4.5L21 12m0 0l-7.5 7.5M21 12H3" />
          </svg>
        </button>
      )}
    </div>
  );
}
