'use client';

import { useRouter } from 'next/navigation';
import type { ApiCitationOut } from '@/lib/api/types';

interface CitationCardProps {
  citation: ApiCitationOut;
  courseId: string;
  index: number;
}

export function CitationCard({ citation, courseId, index }: CitationCardProps) {
  const router = useRouter();

  const locationLabel = citation.page
    ? `p.${citation.page}`
    : citation.slide
    ? `slide ${citation.slide}`
    : null;

  const label = [citation.label || null, locationLabel].filter(Boolean).join(' · ') || 'Source';

  function handleClick() {
    if (!citation.doc_id) return;
    const params = new URLSearchParams();
    if (citation.page) params.set('page', String(citation.page));
    else if (citation.slide) params.set('slide', String(citation.slide));
    const query = params.toString();
    router.push(
      `/courses/${courseId}/documents/${citation.doc_id}/preview${query ? `?${query}` : ''}`,
    );
  }

  const snippet = citation.snippet.length > 160 ? citation.snippet.slice(0, 160) + '…' : citation.snippet;

  return (
    <div
      onClick={citation.doc_id ? handleClick : undefined}
      className={`rounded-md border border-orange-200 bg-orange-50 px-3 py-2 text-xs ${
        citation.doc_id ? 'cursor-pointer hover:bg-orange-100 transition-colors' : ''
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="font-medium text-orange-700 truncate">[{index}] {label}</span>
        <span className="flex-shrink-0 text-orange-500">{Math.round(citation.score * 100)}%</span>
      </div>
      {citation.section && (
        <p className="text-gray-500 mb-1 truncate">{citation.section}</p>
      )}
      <p className="text-gray-700 leading-relaxed">&ldquo;{snippet}&rdquo;</p>
    </div>
  );
}
