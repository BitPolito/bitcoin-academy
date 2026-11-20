'use client';

import { useEffect, useState } from 'react';
import {
  deleteStudySession,
  listStudySessions,
  type StudySession,
} from '@/lib/services/studySessions';

interface SessionHistoryPanelProps {
  courseId: string;
  accessToken?: string;
  currentSessionId: string | null;
  onClose: () => void;
  onResume: (sessionId: string) => void;
  onDeletedCurrent: () => void;
}

function formatWhen(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

/**
 * Past study sessions for this course — resume one or delete it.
 * Server-side persistence (issue #136): sessions survive logout, a browser
 * change, or a different device; this panel is how a student finds them again.
 */
export function SessionHistoryPanel({
  courseId,
  accessToken,
  currentSessionId,
  onClose,
  onResume,
  onDeletedCurrent,
}: SessionHistoryPanelProps) {
  const [sessions, setSessions] = useState<StudySession[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listStudySessions(courseId, accessToken)
      .then((rows) => {
        if (!cancelled) setSessions(rows);
      })
      .catch(() => {
        if (!cancelled) setError('Could not load past sessions.');
      });
    return () => {
      cancelled = true;
    };
  }, [courseId, accessToken]);

  async function handleDelete(sessionId: string) {
    setDeletingId(sessionId);
    try {
      await deleteStudySession(courseId, sessionId, accessToken);
      setSessions((prev) => prev?.filter((s) => s.id !== sessionId) ?? prev);
      if (sessionId === currentSessionId) onDeletedCurrent();
    } catch {
      setError('Could not delete session.');
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <div className="absolute right-0 top-full mt-1 z-20 w-80 b-thin rounded-lg bg-white dark:bg-blue-dark shadow-lg">
      <div className="flex items-center justify-between px-3 py-2 b-thin-b">
        <span className="font-mono text-[10px] tracking-[0.22em] uppercase opacity-70">
          Past sessions
        </span>
        <button onClick={onClose} className="text-xs opacity-60 hover:opacity-100" aria-label="Close">
          ✕
        </button>
      </div>

      {error && <p className="px-3 py-2 text-xs text-red-500">{error}</p>}

      {sessions === null && !error && (
        <p className="px-3 py-3 text-xs opacity-60">Loading…</p>
      )}

      {sessions !== null && sessions.length === 0 && (
        <p className="px-3 py-3 text-xs opacity-60">No past sessions for this course yet.</p>
      )}

      {sessions !== null && sessions.length > 0 && (
        <ul className="max-h-80 overflow-y-auto divide-y divide-current/10">
          {sessions.map((s) => (
            <li key={s.id} className="flex items-center gap-2 px-3 py-2">
              <button
                onClick={() => onResume(s.id)}
                className="flex-1 text-left min-w-0"
                title="Resume this session"
              >
                <div className="text-xs font-medium truncate flex items-center gap-1.5">
                  {s.id === currentSessionId && (
                    <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-500 flex-shrink-0" />
                  )}
                  {s.title || formatWhen(s.started_at)}
                </div>
                <div className="font-mono text-[10px] opacity-60">
                  {s.turn_count} turn{s.turn_count === 1 ? '' : 's'} · {formatWhen(s.last_active_at)}
                </div>
              </button>
              <button
                onClick={() => handleDelete(s.id)}
                disabled={deletingId === s.id}
                className="text-xs opacity-50 hover:opacity-100 hover:text-red-500 disabled:opacity-30"
                title="Delete session"
                aria-label="Delete session"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
