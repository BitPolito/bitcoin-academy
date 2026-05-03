'use client';

import { useCallback, useRef, useState } from 'react';
import {
  uploadDocumentWithProgress,
  fetchDocumentStatus,
  retryDocument,
} from '@/lib/api/documents';
import { ApiError } from '@/lib/api';
import type { MaterialType, ProcessingStage } from '@/lib/api/types';

// ── Constants ──────────────────────────────────────────────────────────────

const MAX_CONCURRENT = 2;
const ALLOWED_EXTS = ['.pdf', '.pptx', '.ppt', '.docx', '.doc', '.txt', '.md'];
const MAX_SIZE_BYTES = 50 * 1024 * 1024;

const MATERIAL_TYPE_LABELS: Record<MaterialType, string> = {
  lecture: 'Lecture',
  past_exam: 'Past Exam',
  supplement: 'Supplement',
};

const STAGE_LABELS: Partial<Record<ProcessingStage, string>> = {
  parsing: 'Parsing',
  normalizing: 'Normalizing',
  chunking: 'Chunking',
  indexing: 'Indexing',
  done: 'Indexed',
  error: 'Error',
};

// ── Types ──────────────────────────────────────────────────────────────────

type UploadStatus = 'queued' | 'uploading' | 'processing' | 'indexed' | 'failed';
type ErrorKind = 'validation' | 'upload' | 'processing' | 'timeout';

interface UploadJob {
  id: string;
  file: File;
  documentType: MaterialType;
  status: UploadStatus;
  uploadPct: number;
  processingStage?: ProcessingStage;
  docId?: string;
  errorKind?: ErrorKind;
  errorMessage?: string;
  retryCount: number;
}

interface DocumentUploadProps {
  courseId: string;
  accessToken?: string;
  onUploadComplete?: () => void;
}

// ── Validation ─────────────────────────────────────────────────────────────

function validateFile(file: File): string | null {
  const ext = '.' + (file.name.split('.').pop() ?? '').toLowerCase();
  if (!ALLOWED_EXTS.includes(ext)) return `Type not supported: ${ext}`;
  if (file.size > MAX_SIZE_BYTES) return 'File too large (max 50 MB)';
  return null;
}

// ── Standalone async runners (no stale closures) ───────────────────────────

async function runUpload(
  jobId: string,
  file: File,
  documentType: string,
  courseId: string,
  accessToken: string | undefined,
  setJobs: React.Dispatch<React.SetStateAction<UploadJob[]>>,
  onRelease: () => void,
  onComplete?: () => void,
): Promise<void> {
  const patch = (p: Partial<UploadJob>) =>
    setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, ...p } : j)));

  try {
    const doc = await uploadDocumentWithProgress(
      courseId,
      file,
      accessToken,
      documentType,
      (pct) => patch({ uploadPct: pct }),
    );
    patch({ docId: doc.id, status: 'processing', uploadPct: 100 });

    for (let i = 0; i < 60; i++) {
      try {
        const s = await fetchDocumentStatus(doc.id, accessToken);
        patch({ processingStage: s.processing_stage });
        if (s.status === 'ready') {
          patch({ status: 'indexed' });
          onComplete?.();
          return;
        }
        if (s.status === 'error') {
          patch({
            status: 'failed',
            errorKind: 'processing',
            errorMessage: s.error_message ?? 'Processing failed',
          });
          onComplete?.();
          return;
        }
      } catch (err) {
        if (!(err instanceof ApiError && err.status >= 500)) throw err;
      }
      await new Promise((r) => setTimeout(r, 3000));
    }
    patch({ status: 'failed', errorKind: 'timeout', errorMessage: 'Processing timed out' });
    onComplete?.();
  } catch (err) {
    patch({
      status: 'failed',
      errorKind: 'upload',
      errorMessage: err instanceof Error ? err.message : 'Upload failed',
    });
    onComplete?.();
  } finally {
    onRelease();
  }
}

async function runRetry(
  jobId: string,
  docId: string,
  accessToken: string | undefined,
  setJobs: React.Dispatch<React.SetStateAction<UploadJob[]>>,
  onComplete?: () => void,
): Promise<void> {
  setJobs((prev) =>
    prev.map((j) =>
      j.id === jobId
        ? {
            ...j,
            status: 'processing',
            processingStage: undefined,
            errorKind: undefined,
            errorMessage: undefined,
            retryCount: j.retryCount + 1,
          }
        : j,
    ),
  );

  const patch = (p: Partial<UploadJob>) =>
    setJobs((prev) => prev.map((j) => (j.id === jobId ? { ...j, ...p } : j)));

  try {
    await retryDocument(docId, accessToken);

    for (let i = 0; i < 60; i++) {
      try {
        const s = await fetchDocumentStatus(docId, accessToken);
        patch({ processingStage: s.processing_stage });
        if (s.status === 'ready') {
          patch({ status: 'indexed' });
          onComplete?.();
          return;
        }
        if (s.status === 'error') {
          patch({
            status: 'failed',
            errorKind: 'processing',
            errorMessage: s.error_message ?? 'Processing failed',
          });
          onComplete?.();
          return;
        }
      } catch (err) {
        if (!(err instanceof ApiError && err.status >= 500)) throw err;
      }
      await new Promise((r) => setTimeout(r, 3000));
    }
    patch({ status: 'failed', errorKind: 'timeout', errorMessage: 'Processing timed out' });
    onComplete?.();
  } catch (err) {
    patch({
      status: 'failed',
      errorKind: 'processing',
      errorMessage: err instanceof Error ? err.message : 'Retry failed',
    });
    onComplete?.();
  }
}

// ── JobRow ─────────────────────────────────────────────────────────────────

function JobRow({
  job,
  onRetry,
  onDismiss,
}: {
  job: UploadJob;
  onRetry?: () => void;
  onDismiss: () => void;
}) {
  const isTerminal = job.status === 'indexed' || job.status === 'failed';
  const isFailed = job.status === 'failed';
  const isActive = job.status === 'uploading' || job.status === 'processing';

  const stageLabel =
    job.status === 'uploading'
      ? `${job.uploadPct}%`
      : job.status === 'processing'
        ? (job.processingStage ? (STAGE_LABELS[job.processingStage] ?? job.processingStage) : 'Processing')
        : job.status === 'indexed'
          ? 'Indexed'
          : job.status === 'queued'
            ? 'Queued'
            : '';

  return (
    <div
      className={`flex flex-col gap-1.5 b-thin rounded-md px-3 py-2 text-sm ${
        isFailed
          ? 'border-red-500/40 bg-red-500/[0.03] dark:border-red-400/30 dark:bg-red-400/[0.04]'
          : ''
      }`}
    >
      <div className="flex items-center gap-2">
        {/* Status icon */}
        {job.status === 'indexed' && (
          <svg
            className="h-4 w-4 flex-shrink-0 text-green-600 dark:text-green-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
        )}
        {isFailed && (
          <svg
            className="h-4 w-4 flex-shrink-0 text-red-500 dark:text-red-400"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={2}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
            />
          </svg>
        )}
        {isActive && (
          <svg
            className="h-4 w-4 flex-shrink-0 animate-spin opacity-50"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
        )}
        {job.status === 'queued' && (
          <svg
            className="h-4 w-4 flex-shrink-0 opacity-35"
            fill="none"
            viewBox="0 0 24 24"
            strokeWidth={1.5}
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        )}

        {/* Filename */}
        <span className="truncate flex-1 font-mono text-[11px]">{job.file.name}</span>

        {/* Stage label */}
        <span
          className={`font-mono text-[10px] flex-shrink-0 ${
            isFailed
              ? 'text-red-500 dark:text-red-400'
              : job.status === 'indexed'
                ? 'text-green-600 dark:text-green-400'
                : 'opacity-50'
          }`}
        >
          {stageLabel}
        </span>

        {/* Retry */}
        {isFailed && job.errorKind !== 'validation' && onRetry && (
          <button
            onClick={onRetry}
            className="flex-shrink-0 font-mono text-[10px] underline text-red-500 dark:text-red-400 hover:opacity-70 transition-opacity"
          >
            Retry
          </button>
        )}

        {/* Dismiss */}
        {isTerminal && (
          <button
            onClick={onDismiss}
            aria-label="Dismiss"
            className="flex-shrink-0 opacity-35 hover:opacity-70 transition-opacity"
          >
            <svg
              className="h-3.5 w-3.5"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth={2}
              stroke="currentColor"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        )}
      </div>

      {/* Upload progress bar */}
      {job.status === 'uploading' && (
        <div className="h-1 w-full rounded-full bg-blue-dark/10 dark:bg-white/10 overflow-hidden">
          <div
            className="h-full rounded-full bg-blue-dark dark:bg-white transition-all duration-150"
            style={{ width: `${job.uploadPct}%` }}
          />
        </div>
      )}

      {/* Error message */}
      {isFailed && job.errorMessage && (
        <p className="font-mono text-[10px] text-red-500 dark:text-red-400 opacity-75 truncate pl-6">
          {job.errorMessage}
        </p>
      )}
    </div>
  );
}

// ── DocumentUpload ─────────────────────────────────────────────────────────

export function DocumentUpload({ courseId, accessToken, onUploadComplete }: DocumentUploadProps) {
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedType, setSelectedType] = useState<MaterialType>('lecture');
  const inputRef = useRef<HTMLInputElement>(null);
  const activeRef = useRef(0);
  const pendingRef = useRef<Array<() => void>>([]);

  const release = useCallback(() => {
    activeRef.current--;
    const next = pendingRef.current.shift();
    if (next) {
      activeRef.current++;
      next();
    }
  }, []);

  const enqueue = useCallback((fn: () => void) => {
    if (activeRef.current < MAX_CONCURRENT) {
      activeRef.current++;
      fn();
    } else {
      pendingRef.current.push(fn);
    }
  }, []);

  const handleFiles = useCallback(
    (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      const newJobs: UploadJob[] = fileArray.map((file) => {
        const validationError = validateFile(file);
        return {
          id: crypto.randomUUID(),
          file,
          documentType: selectedType,
          status: (validationError ? 'failed' : 'queued') as UploadStatus,
          uploadPct: 0,
          errorKind: validationError ? ('validation' as ErrorKind) : undefined,
          errorMessage: validationError ?? undefined,
          retryCount: 0,
        };
      });

      setJobs((prev) => [...prev, ...newJobs]);

      for (const job of newJobs) {
        if (job.status === 'failed') continue;
        const { id, file, documentType } = job;
        enqueue(() => {
          setJobs((prev) =>
            prev.map((j) => (j.id === id ? { ...j, status: 'uploading' } : j)),
          );
          void runUpload(
            id,
            file,
            documentType,
            courseId,
            accessToken,
            setJobs,
            release,
            onUploadComplete,
          );
        });
      }
    },
    [selectedType, courseId, accessToken, enqueue, release, onUploadComplete],
  );

  const handleRetry = useCallback(
    (jobId: string, docId: string) => {
      void runRetry(jobId, docId, accessToken, setJobs, onUploadComplete);
    },
    [accessToken, onUploadComplete],
  );

  const dismissJob = useCallback((jobId: string) => {
    setJobs((prev) => prev.filter((j) => j.id !== jobId));
  }, []);

  const clearDone = useCallback(() => {
    setJobs((prev) => prev.filter((j) => j.status !== 'indexed' && j.status !== 'failed'));
  }, []);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  const doneCount = jobs.filter((j) => j.status === 'indexed' || j.status === 'failed').length;

  return (
    <div>
      {/* Document type selector */}
      <div className="mb-3 flex gap-2">
        {(Object.entries(MATERIAL_TYPE_LABELS) as [MaterialType, string][]).map(([type, label]) => (
          <button
            key={type}
            onClick={() => setSelectedType(type)}
            className={`px-2.5 py-1 rounded text-xs font-mono transition-colors b-thin ${
              selectedType === type
                ? 'bg-blue-dark text-white dark:bg-white dark:text-blue-dark'
                : 'hover:bg-blue-dark/5 dark:hover:bg-white/10 opacity-70'
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Drop zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`relative cursor-pointer rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
          isDragOver
            ? 'border-blue-dark bg-blue-dark/5 dark:border-white dark:bg-white/5'
            : 'border-blue-dark/30 hover:border-blue-dark/60 bg-blue-dark/[0.02] dark:border-white/20 dark:hover:border-white/40'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.pptx,.ppt,.doc,.docx,.txt,.md"
          className="sr-only"
          onChange={(e) => {
            if (e.target.files) handleFiles(e.target.files);
            e.target.value = '';
          }}
        />
        <svg
          className="mx-auto h-8 w-8 opacity-40"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5"
          />
        </svg>
        <p className="mt-2 text-sm">
          <span className="font-medium ink">Click to upload</span>
          <span className="opacity-60"> or drag and drop</span>
        </p>
        <p className="mt-1 font-mono text-[10px] opacity-50">
          PDF · PPTX · DOC · TXT · MD — max 50 MB — as {MATERIAL_TYPE_LABELS[selectedType]}
        </p>
      </div>

      {/* Job list */}
      {jobs.length > 0 && (
        <div className="mt-3 space-y-1.5">
          {jobs.map((job) => (
            <JobRow
              key={job.id}
              job={job}
              onRetry={job.docId ? () => handleRetry(job.id, job.docId!) : undefined}
              onDismiss={() => dismissJob(job.id)}
            />
          ))}
          {doneCount > 1 && (
            <button
              onClick={clearDone}
              className="w-full text-center font-mono text-[10px] opacity-40 hover:opacity-70 transition-opacity pt-0.5"
            >
              Clear done ({doneCount})
            </button>
          )}
        </div>
      )}
    </div>
  );
}
