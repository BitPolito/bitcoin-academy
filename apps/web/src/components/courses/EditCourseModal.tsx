'use client';

import { useState, useEffect, useRef } from 'react';
import type { Course } from '@/lib/services/courses';

interface EditCourseModalProps {
  course: Course;
  onClose: () => void;
  onSave: (title: string, description?: string) => Promise<void>;
}

export function EditCourseModal({ course, onClose, onSave }: EditCourseModalProps) {
  const [title, setTitle] = useState(course.title);
  const [description, setDescription] = useState(course.description ?? '');
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  async function handleSave() {
    if (!title.trim()) {
      setErr('Course title is required.');
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await onSave(title.trim(), description.trim() || undefined);
      onClose();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Failed to update course.');
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-6"
      style={{ background: 'rgba(0,28,224,0.18)' }}
      onClick={onClose}
    >
      <div
        className="b-hard rounded-lg bg-white dark:bg-blue-dark w-full max-w-xl p-7"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <div className="flex items-center gap-2 font-mono text-[11px] tracking-[0.12em] uppercase opacity-70">
            <span>Courses</span>
            <span className="opacity-40">/</span>
            <span className="font-semibold opacity-100 truncate max-w-[160px]">{course.title}</span>
            <span className="opacity-40">/</span>
            <span className="font-semibold opacity-100">Edit</span>
          </div>
          <button
            onClick={onClose}
            className="font-mono text-lg opacity-50 hover:opacity-100 leading-none"
          >
            ×
          </button>
        </div>

        <h2 className="text-2xl font-medium mb-6">Edit course</h2>

        <div className="grid grid-cols-1 gap-4 mb-5">
          <label className="block">
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="font-mono text-[10px] tracking-[0.2em] uppercase opacity-80">
                Course title
              </span>
            </div>
            <input
              ref={inputRef}
              value={title}
              onChange={(e) => {
                setTitle(e.target.value);
                setErr(null);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !saving) handleSave();
              }}
              className="w-full h-10 px-3 b-hard rounded-md bg-transparent outline-none focus:bg-blue-dark/5 dark:focus:bg-white/10"
              placeholder="e.g. Information Theory & Coding"
            />
          </label>
          <label className="block">
            <div className="flex items-baseline justify-between mb-1.5">
              <span className="font-mono text-[10px] tracking-[0.2em] uppercase opacity-80">
                Description
              </span>
              <span className="font-mono text-[10px] opacity-50">optional</span>
            </div>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full h-10 px-3 b-hard rounded-md bg-transparent outline-none focus:bg-blue-dark/5 dark:focus:bg-white/10"
              placeholder="Short description or notes"
            />
          </label>
        </div>

        {err && (
          <div
            className="mb-4 font-mono text-[11px] px-3 py-2 rounded-md"
            style={{ background: '#b3261e18', color: '#b3261e' }}
          >
            {err}
          </div>
        )}

        <div className="flex items-center justify-end gap-2 b-thin-t pt-4">
          <button className="btn-ghost" onClick={onClose} disabled={saving}>
            Cancel
          </button>
          <button className="btn-primary" onClick={handleSave} disabled={saving || !title.trim()}>
            {saving ? 'Saving…' : 'Save changes →'}
          </button>
        </div>
      </div>
    </div>
  );
}
