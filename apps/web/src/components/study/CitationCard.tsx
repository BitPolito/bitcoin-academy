'use client';

import { useRouter } from 'next/navigation';
import type { EvidenceChunk } from '@/lib/api/types';

interface CitationCardProps {
  chunk: EvidenceChunk;
  courseId: string;
  index: number;
}

export function CitationCard({ chunk, courseId, index }: CitationCardProps) {
  const router = useRouter();
  const { anchor } = chunk;

  const locationLabel = anchor.page
    ? `p.${anchor.page}`
    : anchor.slide
    ? `slide ${anchor.slide}`
    : null;

  const label = [anchor.doc_name, locationLabel].filter(Boolean).join(' · ');

  function handleClick() {
    if (!anchor.doc_id) return;
    const params = new URLSearchParams();
    if (anchor.page) params.set('page', String(anchor.page));
    else if (anchor.slide) params.set('slide', String(anchor.slide));
    const query = params.toString();
    router.push(
      `/courses/${courseId}/documents/${anchor.doc_id}/preview${query ? `?${query}` : ''}`,
    );
  }

  const snippet = chunk.text.length > 160 ? chunk.text.slice(0, 160) + '…' : chunk.text;

  return (
    <div
      onClick={anchor.doc_id ? handleClick : undefined}
      className={`rounded-md border border-orange-200 bg-orange-50 px-3 py-2 text-xs ${
        anchor.doc_id ? 'cursor-pointer hover:bg-orange-100 transition-colors' : ''
      }`}
    >
      <div className="flex items-center justify-between gap-2 mb-1">
        <span className="font-medium text-orange-700 truncate">[{index}] {label}</span>
        <span className="flex-shrink-0 text-orange-500">{Math.round(chunk.score * 100)}%</span>
      </div>
      {anchor.section && (
        <p className="text-gray-500 mb-1 truncate">{anchor.section}</p>
      )}
      <p className="text-gray-700 leading-relaxed">&ldquo;{snippet}&rdquo;</p>
    </div>
  );
}
