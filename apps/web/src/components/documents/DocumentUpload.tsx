'use client';

import { useCallback, useRef, useState } from 'react';
import { uploadDocument, pollDocumentUntilTerminal } from '@/lib/api/documents';

interface DocumentUploadProps {
  courseId: string;
  accessToken?: string;
  onUploadComplete?: () => void;
}

interface UploadJob {
  file: File;
  progress: 'uploading' | 'processing' | 'done' | 'error';
  errorMessage?: string;
}

export function DocumentUpload({ courseId, accessToken, onUploadComplete }: DocumentUploadProps) {
  const [jobs, setJobs] = useState<UploadJob[]>([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: FileList | File[]) => {
      const fileArray = Array.from(files);
      if (fileArray.length === 0) return;

      const newJobs: UploadJob[] = fileArray.map((file) => ({
        file,
        progress: 'uploading' as const,
      }));

      setJobs((prev) => [...prev, ...newJobs]);

      for (let i = 0; i < fileArray.length; i++) {
        const file = fileArray[i];
        const jobIndex = jobs.length + i;

        try {
          const doc = await uploadDocument(courseId, file, accessToken);

          setJobs((prev) => {
            const updated = [...prev];
            if (updated[jobIndex]) updated[jobIndex] = { ...updated[jobIndex], progress: 'processing' };
            return updated;
          });

          await pollDocumentUntilTerminal(doc.id, accessToken);

          setJobs((prev) => {
            const updated = [...prev];
            if (updated[jobIndex]) updated[jobIndex] = { ...updated[jobIndex], progress: 'done' };
            return updated;
          });

          onUploadComplete?.();
        } catch (err) {
          const message = err instanceof Error ? err.message : 'Upload failed';
          setJobs((prev) => {
            const updated = [...prev];
            if (updated[jobIndex])
              updated[jobIndex] = { ...updated[jobIndex], progress: 'error', errorMessage: message };
            return updated;
          });
          onUploadComplete?.();
        }
      }
    },
    [courseId, accessToken, jobs.length, onUploadComplete]
  );

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        handleFiles(e.dataTransfer.files);
      }
    },
    [handleFiles]
  );

  const activeJobs = jobs.filter((j) => j.progress === 'uploading' || j.progress === 'processing');
  const errorJobs = jobs.filter((j) => j.progress === 'error');

  return (
    <div>
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
            ? 'border-orange-400 bg-orange-50'
            : 'border-gray-300 hover:border-gray-400 bg-gray-50'
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
        <svg className="mx-auto h-8 w-8 text-gray-400" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5m-13.5-9L12 3m0 0l4.5 4.5M12 3v13.5" />
        </svg>
        <p className="mt-2 text-sm text-gray-600">
          <span className="font-medium text-orange-600">Click to upload</span> or drag and drop
        </p>
        <p className="mt-1 text-xs text-gray-400">PDF, PPTX, DOC, TXT, MD</p>
      </div>

      {activeJobs.length > 0 && (
        <div className="mt-3 space-y-2">
          {activeJobs.map((job, i) => (
            <div key={i} className="flex items-center gap-2 text-sm text-gray-600">
              <svg className="h-4 w-4 animate-spin text-orange-500" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              <span className="truncate flex-1">{job.file.name}</span>
              <span className="text-xs text-gray-400 capitalize">{job.progress}</span>
            </div>
          ))}
        </div>
      )}

      {errorJobs.length > 0 && (
        <div className="mt-3 space-y-2">
          {errorJobs.map((job, i) => (
            <div key={i} className="flex items-center gap-2 rounded bg-red-50 px-3 py-2 text-sm">
              <svg className="h-4 w-4 text-red-500 flex-shrink-0" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
              </svg>
              <span className="truncate flex-1 text-red-700">{job.file.name}</span>
              <span className="text-xs text-red-500">{job.errorMessage}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
