'use client';

import { useCallback, useRef, useState } from 'react';
import { uploadDocument, retryDocument, pollDocumentUntilTerminal } from '@/lib/api/documents';
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
        onUploadComplete?.();
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Upload failed';
        updateJob(jobIndex, { progress: 'error', errorMessage: message });
        onUploadComplete?.();
      }
    },
    [courseId, accessToken, onUploadComplete, updateJob],
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
      onUploadComplete?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Retry failed';
      updateJob(jobIndex, { progress: 'error', errorMessage: message });
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
            className={`px-2.5 py-1 rounded-full text-xs font-medium border transition-colors ${
              selectedType === type
                ? 'bg-orange-600 text-white border-orange-600'
                : 'bg-white text-gray-600 border-gray-300 hover:border-orange-400'
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
          isDragOver ? 'border-orange-400 bg-orange-50' : 'border-gray-300 hover:border-gray-400 bg-gray-50'
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
        <svg className="mx-auto h-8 w-8 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
        </svg>
        <p className="mt-2 text-sm text-gray-600">
          <span className="font-medium text-orange-600">Click to upload</span> or drag and drop
        </p>
        <p className="mt-1 text-xs text-gray-400">PDF, PPTX, DOC, TXT, MD · as {MATERIAL_TYPE_LABELS[selectedType]}</p>
      </div>

      {/* Active jobs */}
      {activeJobs.length > 0 && (
        <div className="mt-3 space-y-2">
          {activeJobs.map((job, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-gray-600">
              <svg className="h-4 w-4 animate-spin text-orange-500 flex-shrink-0" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
              </svg>
              <span className="truncate flex-1">{job.file.name}</span>
              <span className="text-xs text-gray-400 capitalize">{job.progress}</span>
            </div>
          ))}
        </div>
      )}

      {/* Error jobs with retry */}
      {errorJobs.length > 0 && (
        <div className="mt-3 space-y-2">
          {errorJobs.map((job) => (
            <div key={job.index} className="flex items-center gap-2 rounded bg-red-50 px-3 py-2 text-sm">
              <svg className="h-4 w-4 text-red-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
              <span className="truncate flex-1 text-red-700">{job.file.name}</span>
              <span className="text-xs text-red-500 truncate max-w-32">{job.errorMessage}</span>
              {job.docId && (
                <button
                  onClick={() => handleRetry(job.index)}
                  className="flex-shrink-0 text-xs font-medium text-red-700 hover:text-red-900 underline"
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
