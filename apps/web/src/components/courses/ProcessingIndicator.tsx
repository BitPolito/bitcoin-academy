'use client';

import type { DocumentStatus, ProcessingStage } from '@/lib/api/types';

interface ProcessingIndicatorProps {
  status: DocumentStatus;
  stage?: ProcessingStage;
  className?: string;
}

const STATUS_CONFIG: Record<DocumentStatus, { label: string; bg: string; text: string; dot: string }> = {
  uploading: {
    label: 'Uploading',
    bg: 'bg-blue-50',
    text: 'text-blue-700',
    dot: 'bg-blue-500 animate-pulse',
  },
  processing: {
    label: 'Processing',
    bg: 'bg-yellow-50',
    text: 'text-yellow-700',
    dot: 'bg-yellow-500 animate-pulse',
  },
  ready: {
    label: 'Ready',
    bg: 'bg-green-50',
    text: 'text-green-700',
    dot: 'bg-green-500',
  },
  error: {
    label: 'Error',
    bg: 'bg-red-50',
    text: 'text-red-700',
    dot: 'bg-red-500',
  },
};

const STAGE_LABELS: Record<ProcessingStage, string> = {
  queued: 'Queued',
  uploading: 'Uploading',
  parsing: 'Parsing',
  normalizing: 'Normalizing',
  chunking: 'Chunking',
  indexing: 'Indexing',
  done: 'Done',
  error: 'Error',
};

export function ProcessingIndicator({ status, stage, className = '' }: ProcessingIndicatorProps) {
  const config = STATUS_CONFIG[status];
  const stageLabel = stage && stage !== 'done' && stage !== 'error' ? STAGE_LABELS[stage] : null;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium ${config.bg} ${config.text} ${className}`}
    >
      <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      {config.label}
      {stageLabel && status === 'processing' && (
        <span className="opacity-75">· {stageLabel}</span>
      )}
    </span>
  );
}
