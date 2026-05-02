'use client';

import { useCallback, useRef, useState } from 'react';
import { uploadDocument, retryDocument, pollDocumentUntilTerminal } from '@/lib/api/documents';
import { useToast } from '@/components/ui/Toast';
import type { MaterialType } from '@/lib/api/types';

interface DocumentUploadProps {
  courseId: string;
  accessToken?: string;
  onUploadComplete?: () => void;
}

interface UploadJob {
  docId?: string;
  file: File;
  documentType: MaterialType;
  progress: 'uploading' | 'processing' | 'done' | 'error';
  errorMessage?: string;
}

const MATERIAL_TYPE_LABELS: Record<MaterialType, string> = {
  lecture: 'Lecture',
  past_exam: 'Past Exam',
  supplement: 'Supplement',
};

export function DocumentUpload({ courseId, accessToken, onUploadComplete }: DocumentUploadProps) {
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [selectedType, setSelectedType] = useState<MaterialType>('lecture');
  const inputRef = useRef<HTMLInputElement>(null);
  const { showToast } = useToast();

  const updateJob = useCallback((index: number, patch: Partial<UploadJob>) => {
    setJobs((prev) => {
      const updated = [...prev];
      if (updated[index]) updated[index] = { ...updated[index], ...patch };
      return updated;
    });
  }, []);

  const processFile = useCallback(
    async (file: File, documentType: MaterialType, jobIndex: number) => {
      try {
        const doc = await uploadDocument(courseId, file, accessToken, documentType);
        updateJob(jobIndex, { docId: doc.id, progress: 'processing' });

        await pollDocumentUntilTerminal(doc.id, accessToken);
        updateJob(jobIndex, { progress: 'done' });
        showToast(`${file.name} indexed`, 'ok');
        onUploadComplete?.();
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Upload failed';
        updateJob(jobIndex, { progress: 'error', errorMessage: message });
        showToast(`${file.name}: ${message}`, 'err');
        onUploadComplete?.();
      }
    },
    [courseId, accessToken, onUploadComplete, updateJob, showToast],
  );

  const handleFiles = useCallback(
    (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      const startIndex = jobs.length;
      const newJobs: UploadJob[] = fileArray.map((file) => ({
        file,
        documentType: selectedType,
        progress: 'uploading' as const,
      }));
      setJobs((prev) => [...prev, ...newJobs]);

      fileArray.forEach((file, i) => {
        processFile(file, selectedType, startIndex + i);
      });
    },
    [jobs.length, selectedType, processFile],
  );

  async function handleRetry(jobIndex: number) {
    const job = jobs[jobIndex];
    if (!job?.docId) return;

    updateJob(jobIndex, { progress: 'processing', errorMessage: undefined });
    try {
      await retryDocument(job.docId, accessToken);
      await pollDocumentUntilTerminal(job.docId, accessToken);
      updateJob(jobIndex, { progress: 'done' });
      showToast(`${job.file.name} indexed`, 'ok');
      onUploadComplete?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Retry failed';
      updateJob(jobIndex, { progress: 'error', errorMessage: message });
      showToast(`${job.file.name}: ${message}`, 'err');
    }
  }

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      if (e.dataTransfer.files.length > 0) handleFiles(e.dataTransfer.files);
    },
    [handleFiles],
  );

  const activeJobs = jobs.filter((j) => j.progress === 'uploading' || j.progress === 'processing');
  const errorJobs = jobs
    .map((j, i) => ({ ...j, index: i }))
    .filter((j) => j.progress === 'error');

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
        onDragOver={(e) => { e.preventDefault(); setIsDragOver(true); }}
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
          onChange={(e) => { if (e.target.files) handleFiles(e.target.files); e.target.value = ''; }}
        />
        <svg
          className="mx-auto h-8 w-8 opacity-40"
          fill="none"
          viewBox="0 0 24 24"
          strokeWidth={1.5}
          stroke="currentColor"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
        </svg>
        <p className="mt-2 text-sm">
          <span className="font-medium ink">Click to upload</span>
          <span className="opacity-60"> or drag and drop</span>
        </p>
        <p className="mt-1 font-mono text-[10px] opacity-50">
          PDF · PPTX · DOC · TXT · MD — as {MATERIAL_TYPE_LABELS[selectedType]}
        </p>
      </div>

      {/* Active jobs */}
      {activeJobs.length > 0 && (
        <div className="mt-3 space-y-2">
          {activeJobs.map((job, i) => (
            <div key={i} className="flex items-center gap-2 text-sm b-thin rounded-md px-3 py-2">
              <svg className="h-4 w-4 animate-spin flex-shrink-0 opacity-60" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="truncate flex-1 font-mono text-[11px]">{job.file.name}</span>
              <span className="font-mono text-[10px] opacity-50 capitalize">{job.progress}</span>
            </div>
          ))}
        </div>
      )}

      {/* Error jobs with retry */}
      {errorJobs.length > 0 && (
        <div className="mt-3 space-y-2">
          {errorJobs.map((job) => (
            <div key={job.index} className="flex items-center gap-2 b-thin rounded-md px-3 py-2 text-sm" style={{ borderColor: 'rgba(179,38,30,0.4)', background: 'rgba(179,38,30,0.04)' }}>
              <svg className="h-4 w-4 flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="#b3261e">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
              <span className="truncate flex-1 font-mono text-[11px]" style={{ color: '#b3261e' }}>{job.file.name}</span>
              <span className="font-mono text-[10px] truncate max-w-[8rem] opacity-70" style={{ color: '#b3261e' }}>
                {job.errorMessage}
              </span>
              {job.docId && (
                <button
                  onClick={() => handleRetry(job.index)}
                  className="flex-shrink-0 font-mono text-[10px] underline opacity-80 hover:opacity-100 transition-opacity"
                  style={{ color: '#b3261e' }}
                >
                  Retry
                </button>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
