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
  const snippet = citation.snippet.length > 180 ? citation.snippet.slice(0, 180) + '…' : citation.snippet;

  function handleClick() {
    if (!citation.doc_id) return;
    const params = new URLSearchParams();
    if (citation.page) params.set('page', String(citation.page));
    else if (citation.slide) params.set('slide', String(citation.slide));
    const query = params.toString();
    router.push(`/courses/${courseId}/documents/${citation.doc_id}/preview${query ? `?${query}` : ''}`);
  }

  return (
    <div
      onClick={citation.doc_id ? handleClick : undefined}
      className={`b-thin rounded-md px-3 py-2.5 ${citation.doc_id ? 'cursor-pointer hover:bg-blue-dark/5 transition-colors' : ''}`}
    >
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <span className="font-mono text-[10px] tracking-[0.18em] uppercase opacity-70 truncate">
          [{index}] {label}
        </span>
        <span className="font-mono text-[10px] opacity-60 flex-shrink-0">
          {Math.round(citation.score * 100)}%
        </span>
      </div>
      {citation.section && (
        <p className="font-mono text-[10px] opacity-50 mb-1 truncate">{citation.section}</p>
      )}
      <p className="text-[12.5px] leading-snug opacity-90">&ldquo;{snippet}&rdquo;</p>
    </div>
  );
}
