'use client';

import { useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import type { DocumentListRow, MaterialType } from '@/lib/api/types';
import { deleteDocument } from '@/lib/api/documents';
import { ProcessingIndicator } from '@/components/courses/ProcessingIndicator';

interface DocumentRowProps {
  document: DocumentListRow;
  accessToken?: string;
  onDeleted?: () => void;
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const TYPE_BADGE: Record<MaterialType, { label: string; className: string }> = {
  lecture:    { label: 'Lecture',    className: 'bg-blue-100 text-blue-700' },
  past_exam:  { label: 'Past Exam',  className: 'bg-purple-100 text-purple-700' },
  supplement: { label: 'Supplement', className: 'bg-gray-100 text-gray-600' },
};

export function DocumentRow({ document: doc, accessToken, onDeleted }: DocumentRowProps) {
  const [deleting, setDeleting] = useState(false);
  const router = useRouter();
  const params = useParams();
  const courseId = params.courseId as string;

  const typeBadge = TYPE_BADGE[doc.documentType] ?? TYPE_BADGE.lecture;

  async function handleDelete() {
    if (!confirm(`Delete "${doc.filename}"?`)) return;
    setDeleting(true);
    try {
      await deleteDocument(doc.id, accessToken);
      onDeleted?.();
    } catch {
      setDeleting(false);
    }
  }

  function handlePreview() {
    router.push(`/courses/${courseId}/documents/${doc.id}/preview`);
  }

  return (
    <div className="flex items-center gap-3 py-3 px-1 group">
      <div className="flex-shrink-0">
        <svg className="h-7 w-7 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
        </svg>
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm font-medium text-gray-900 truncate">{doc.filename}</p>
          <span className={`inline-flex px-1.5 py-0.5 rounded text-[10px] font-semibold ${typeBadge.className}`}>
            {typeBadge.label}
          </span>
        </div>
        <p className="text-xs text-gray-500">{formatFileSize(doc.size)}</p>
      </div>

      <ProcessingIndicator status={doc.status} />

      {/* Preview link */}
      <button
        onClick={handlePreview}
        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600"
        title="View preview"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M2.036 12.322a1.012 1.012 0 010-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      </button>

      {/* Delete */}
      <button
        onClick={handleDelete}
        disabled={deleting}
        className="opacity-0 group-hover:opacity-100 transition-opacity p-1 rounded hover:bg-red-50 text-gray-400 hover:text-red-500 disabled:opacity-50"
        title="Delete document"
      >
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
        </svg>
      </button>
    </div>
  );
}
